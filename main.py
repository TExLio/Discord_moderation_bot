import discord
from discord.ext import commands
import re
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Needed to read messages

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------
# CONFIGURATION
# ------------------------------
TOXIC_WORDS = ["badword1", "badword2", "spamword"]  # Add your list
SPAM_LINK_PATTERN = re.compile(r"(https?://\S+)")
RAID_PATTERNS = ["!!!", "@everyone"]  # Example raid triggers
LOG_FILE = "infractions.csv"

# Initialize log file
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=["user", "action", "reason", "time"]).to_csv(LOG_FILE, index=False)

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def log_infraction(user, action, reason):
    df = pd.read_csv(LOG_FILE)
    df = df.append({"user": str(user), "action": action, "reason": reason, "time": datetime.now()}, ignore_index=True)
    df.to_csv(LOG_FILE, index=False)

def check_toxic(message):
    for word in TOXIC_WORDS:
        if word in message.content.lower():
            return True
    if SPAM_LINK_PATTERN.search(message.content):
        return True
    for pattern in RAID_PATTERNS:
        if pattern in message.content:
            return True
    return False

# ------------------------------
# EVENTS
# ------------------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore bot messages

    # Check for toxic content
    if check_toxic(message):
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, your message was removed due to inappropriate content.")
            log_infraction(message.author, "Deleted Message", "Toxic/Spam/Raid content")
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
    log_infraction(member, "Warned", reason)

@bot.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} was kicked. Reason: {reason}")
    log_infraction(member, "Kicked", reason)

@bot.command()
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member, duration: int = 10):
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not role:
        # Create Muted role if it doesn't exist
        role = await ctx.guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False))
        for channel in ctx.guild.channels:
            await channel.set_permissions(role, send_messages=False)

    await member.add_roles(role)
    await ctx.send(f"{member.mention} has been muted for {duration} minutes.")
    log_infraction(member, "Muted", f"Duration: {duration} minutes")

    # Unmute after duration
    await discord.utils.sleep_until(datetime.utcnow() + pd.Timedelta(minutes=duration))
    await member.remove_roles(role)
    await ctx.send(f"{member.mention} has been unmuted.")

# ------------------------------
# DASHBOARD COMMAND
# ------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def infractions(ctx):
    df = pd.read_csv(LOG_FILE)
    if df.empty:
        await ctx.send("No infractions logged yet.")
    else:
        embed = discord.Embed(title="Infractions Log", color=discord.Color.red())
        for i, row in df.tail(10).iterrows():
            embed.add_field(name=row['user'], value=f"Action: {row['action']}\nReason: {row['reason']}\nTime: {row['time']}", inline=False)
        await ctx.send(embed=embed)

# ------------------------------
bot.run(TOKEN)
