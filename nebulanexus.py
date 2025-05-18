import discord
from discord.ext import tasks
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
bot.run(os.getenv("DISCORD_TOKEN"))


intents = discord.Intents.default()
intents.members = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.punishment_logs = {}
        

    async def setup_hook(self):
        await self.tree.sync()

bot = MyClient()

ALLOWED_ALL = ["moderator", "trainee", "administrator","owner :3"]
ALLOWED_ELEVATED = ["moderator", "administrator"]

def has_role(user: discord.Member, roles: list[str]) -> bool:
    return any(role.name.lower() in roles for role in user.roles)

def is_allowed(interaction: discord.Interaction):
    return has_role(interaction.user, ALLOWED_ALL)

def is_elevated(interaction: discord.Interaction):
    return has_role(interaction.user, ALLOWED_ELEVATED) or interaction.user.guild_permissions.administrator

def log_punishment(bot, user_id, action, reason):
    if user_id not in bot.punishment_logs:
        bot.punishment_logs[user_id] = []
    bot.punishment_logs[user_id].append((action, reason))

async def send_dm(user: discord.Member, title: str, reason: str):
    try:
        await user.send(f"**{title}**\nReason: {reason}")
    except:
        pass

@bot.tree.command(name="betterban", description="Ban a user with a reason")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def betterban(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_elevated(interaction):
        return await interaction.response.send_message("You don’t have permission to ban users.", ephemeral=True)
    
    try:
        await send_dm(user, "You have been banned", reason)
        log_punishment(bot, user.id, "Ban", reason)
        await user.ban(reason=reason)
        await interaction.response.send_message(f"{user} has been banned.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don’t have permission to ban this user.", ephemeral=True)

@bot.tree.command(name="bettermute", description="Mute a user for a number of seconds")
@app_commands.describe(user="User to mute", duration="Duration in seconds", reason="Reason for mute")
async def bettermute(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    await send_dm(user, f"You have been muted for {duration} seconds", reason)
    log_punishment(bot, user.id, f"Mute ({duration}s)", reason)

    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False)

    await user.add_roles(muted_role)
    await interaction.response.send_message(f"{user} has been muted for {duration} seconds.", ephemeral=True)

    await asyncio.sleep(duration)
    await user.remove_roles(muted_role)

@bot.tree.command(name="betterwarn", description="Warn a user with a reason")
@app_commands.describe(user="User to warn", reason="Reason for warning")
async def betterwarn(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    await send_dm(user, "You have been warned", reason)
    log_punishment(bot, user.id, "Warn", reason)
    await interaction.response.send_message(f"{user} has been warned.", ephemeral=True)

@bot.tree.command(name="betterlogs", description="See all punishments for a user")
@app_commands.describe(user="User to view logs for")
async def betterlog(interaction: discord.Interaction, user: discord.Member):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    logs = bot.punishment_logs.get(user.id, [])
    if not logs:
        return await interaction.response.send_message("No logs found for this user.", ephemeral=True)

    embed = discord.Embed(title=f"Punishment Log for {user}", color=discord.Color.red())
    for i, (action, reason) in enumerate(logs, 1):
        embed.add_field(name=f"{i}. {action}", value=reason, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="betterunmute", description="Unmute a user")
@app_commands.describe(user="User to unmute")
async def betterunmute(interaction: discord.Interaction, user: discord.Member):
    if not is_allowed(interaction):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)

    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if muted_role in user.roles:
        await user.remove_roles(muted_role)
        await interaction.response.send_message(f"{user} has been unmuted.", ephemeral=True)
    else:
        await interaction.response.send_message(f"{user} is not muted.", ephemeral=True)

@bot.tree.command(name="betterunban", description="Unban a user by ID")
@app_commands.describe(user_id="The user ID to unban")
async def betterunban(interaction: discord.Interaction, user_id: str):
    if not is_elevated(interaction):
        return await interaction.response.send_message("You don’t have permission to unban users.", ephemeral=True)

    try:
        banned_users = await interaction.guild.bans()
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

    logs = bot.punishment_logs.get(user.id, [])
    if not logs or entry_number < 1 or entry_number > len(logs):
        return await interaction.response.send_message("Invalid log entry number.", ephemeral=True)

    removed = logs.pop(entry_number - 1)
    await interaction.response.send_message(
        f"Removed log entry #{entry_number} for {user}: {removed[0]} - {removed[1]}", ephemeral=True
    )

