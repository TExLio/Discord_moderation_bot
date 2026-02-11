import os
import discord
from discord.ext import commands, tasks
import re
from datetime import datetime, timedelta
import aiosqlite
from dotenv import load_dotenv

# ------------------------------
# LOAD ENV VARIABLES
# ------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN not set!")

# ------------------------------
# INTENTS & BOT SETUP
# ------------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------
# CONFIGURATION
# ------------------------------
TOXIC_WORDS = ["badword1", "badword2", "spamword"]  # Example
SPAM_LINK_PATTERN = re.compile(r"(https?://\S+)")
RAID_PATTERNS = ["!!!", "@everyone"]  # Example raid triggers
DB_FILE = "infractions.db"

# ------------------------------
# DATABASE INITIALIZATION
# ------------------------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS infractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            reason TEXT,
            time TEXT
        )
        """)
        await db.commit()

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
async def log_infraction(guild_id, user, action, reason):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO infractions (guild_id, user_id, username, action, reason, time) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user.id, str(user), action, reason, datetime.utcnow().isoformat())
        )
        await db.commit()

def check_toxic(message):
    text = message.content.lower()
    if any(word in text for word in TOXIC_WORDS):
        return True
    if SPAM_LINK_PATTERN.search(message.content):
        return True
    if any(pattern in message.content for pattern in RAID_PATTERNS):
        return True
    return False

# ------------------------------
# EVENTS
# ------------------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await init_db()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore bot messages

    if check_toxic(message):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention}, your message was removed due to inappropriate content.",
                delete_after=5
            )
            await log_infraction(message.guild.id, message.author, "Deleted Message", "Toxic/Spam/Raid content")
        except Exception as e:
            print("Error deleting message:", e)

    await bot.process_commands(message)

# ------------------------------
# COMMANDS FOR ADMINS
# ------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    await ctx.send(f"{member.mention} has been warned. Reason: {reason}")
    await log_infraction(ctx.guild.id, member, "Warned", reason)

@bot.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} was kicked. Reason: {reason}")
    await log_infraction(ctx.guild.id, member, "Kicked", reason)

@bot.command()
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member, duration: int = 10):
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not role:
        role = await ctx.guild.create_role(
            name="Muted", permissions=discord.Permissions(send_messages=False)
        )
        for channel in ctx.guild.channels:
            await channel.set_permissions(role, send_messages=False)

    await member.add_roles(role)
    await ctx.send(f"{member.mention} has been muted for {duration} minutes.")
    await log_infraction(ctx.guild.id, member, "Muted", f"Duration: {duration} minutes")

    # Unmute after duration
    await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=duration))
    await member.remove_roles(role)
    await ctx.send(f"{member.mention} has been unmuted.")

# ------------------------------
# DASHBOARD COMMAND
# ------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def infractions(ctx):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT username, action, reason, time FROM infractions WHERE guild_id=? ORDER BY id DESC LIMIT 10",
            (ctx.guild.id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("No infractions logged yet.")
        return

    embed = discord.Embed(title="Infractions Log", color=discord.Color.red())
    for row in rows:
        username, action, reason, time = row
        embed.add_field(
            name=username,
            value=f"Action: {action}\nReason: {reason}\nTime: {time}",
            inline=False
        )
    await ctx.send(embed=embed)

# ------------------------------
bot.run(TOKEN)
