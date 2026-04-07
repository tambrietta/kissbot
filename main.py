import os
import sqlite3
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple


import discord
from discord import app_commands
from discord.ext import commands

HEADPAT_COST = 10
EMBED_COLOR = 0xF5B7D2
DEFAULT_DB_PATH = Path("kissbot.sqlite3")


def normalize_db_path(db_path: Path) -> Path:
    path = Path(db_path)
    if path.parent and path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    return path



def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = normalize_db_path(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kiss_totals (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            kisses INTEGER NOT NULL DEFAULT 0 CHECK(kisses >= 0),
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    conn.commit()
    return conn


class KissStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = normalize_db_path(db_path)
        with get_connection(self.db_path):
            pass

    def get_kiss_total(self, guild_id: int, user_id: int) -> int:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT kisses FROM kiss_totals WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return int(row["kisses"]) if row else 0

    def set_kiss_total(self, guild_id: int, user_id: int, total: int) -> None:
        total = max(0, int(total))
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO kiss_totals (guild_id, user_id, kisses)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET kisses = excluded.kisses
                """,
                (guild_id, user_id, total),
            )
            conn.commit()

    def add_kisses(self, guild_id: int, user_id: int, amount: int) -> int:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO kiss_totals (guild_id, user_id, kisses)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET kisses = kiss_totals.kisses + excluded.kisses
                """,
                (guild_id, user_id, amount),
            )
            row = conn.execute(
                "SELECT kisses FROM kiss_totals WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            conn.commit()
            return int(row["kisses"]) if row else 0

    def remove_kisses(self, guild_id: int, user_id: int, amount: int) -> int:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO kiss_totals (guild_id, user_id, kisses)
                VALUES (?, ?, 0)
                ON CONFLICT(guild_id, user_id)
                DO NOTHING
                """,
                (guild_id, user_id),
            )
            conn.execute(
                """
                UPDATE kiss_totals
                SET kisses = MAX(0, kisses - ?)
                WHERE guild_id = ? AND user_id = ?
                """,
                (amount, guild_id, user_id),
            )
            row = conn.execute(
                "SELECT kisses FROM kiss_totals WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            conn.commit()
            return int(row["kisses"]) if row else 0

    def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Tuple[int, int]]:
        limit = max(1, int(limit))
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT user_id, kisses
                FROM kiss_totals
                WHERE guild_id = ? AND kisses > 0
                ORDER BY kisses DESC, user_id ASC
                LIMIT ?
                """,
                (guild_id, limit),
            ).fetchall()
            return [(int(row["user_id"]), int(row["kisses"])) for row in rows]



def progress_count(total: int) -> int:
    return max(0, int(total)) % HEADPAT_COST



def progress_bar(total: int) -> str:
    progress = progress_count(total)
    return "★" * progress + "☆" * (HEADPAT_COST - progress)



def redeemable_headpats(total: int) -> int:
    return max(0, int(total)) // HEADPAT_COST



def kiss_word(amount: int) -> str:
    return "kiss" if int(amount) == 1 else "kisses"



def head_pat_word(amount: int) -> str:
    return "head pat" if int(amount) == 1 else "head pats"



def get_token() -> Optional[str]:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    return token or None



def get_test_guild_id() -> Optional[int]:
    raw = os.getenv("TEST_GUILD_ID", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None



def make_embed_for_kiss(user_display_name: str, total: int, amount: int) -> discord.Embed:
    progress = progress_count(total)
    redeemable = redeemable_headpats(total)
    embed = discord.Embed(
        title=f"{user_display_name} got {amount} forehead {kiss_word(amount)}",
        description=f"**Total kisses earned:** {total}",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Progress", value=f"`{progress_bar(total)}` ({progress}/{HEADPAT_COST})", inline=False)
    embed.add_field(name="Redeem", value=f"You can redeem {HEADPAT_COST} forehead kisses for 1 headpat", inline=False)
    embed.set_footer(text=f"Redeemable head pats: {redeemable}")
    return embed



def make_embed_for_check(user_display_name: str, total: int) -> discord.Embed:
    progress = progress_count(total)
    redeemable = redeemable_headpats(total)
    embed = discord.Embed(
        title=f"Forehead Kiss Ledger for {user_display_name}",
        description=f"**Total kisses earned:** {total}",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Progress", value=f"`{progress_bar(total)}` ({progress}/{HEADPAT_COST})", inline=False)
    embed.add_field(name="Redeem", value=f"You can redeem {HEADPAT_COST} forehead kisses for 1 headpat", inline=False)
    embed.set_footer(text=f"Redeemable head pats: {redeemable}")
    return embed



def make_embed_for_redeem(user_display_name: str, head_pats: int, cost: int, new_total: int) -> discord.Embed:
    progress = progress_count(new_total)
    redeemable = redeemable_headpats(new_total)
    embed = discord.Embed(
        title=f"{user_display_name} redeemed {head_pats} {head_pat_word(head_pats)}",
        description=f"**{cost} kisses spent.**\n**Kisses remaining:** {new_total}",
        color=EMBED_COLOR,
    )
    embed.add_field(name="Progress", value=f"`{progress_bar(new_total)}` ({progress}/{HEADPAT_COST})", inline=False)
    embed.add_field(name="Redeem", value=f"You can redeem {HEADPAT_COST} forehead kisses for 1 headpat", inline=False)
    embed.set_footer(text=f"Redeemable head pats remaining: {redeemable}")
    return embed


class KissBot(commands.Bot):
    def __init__(self, store: KissStore) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.store = store

    async def setup_hook(self) -> None:
        guild_id = get_test_guild_id()
        if guild_id is not None:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()



def build_bot(store: Optional[KissStore] = None) -> KissBot:
    bot = KissBot(store or KissStore())

    @bot.event
    async def on_ready() -> None:
        if bot.user is not None:
            print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("Kiss ledger is awake.")

    @bot.tree.command(name="kiss", description="Give someone forehead kisses.")
    @app_commands.describe(user="Who gets the forehead kisses?", amount="How many kisses to give?")
    async def kiss(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 100]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        new_total = bot.store.add_kisses(interaction.guild.id, user.id, amount)
        embed = make_embed_for_kiss(user.display_name, new_total, amount)
        await interaction.response.send_message(
            content=user.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @bot.tree.command(name="kisscheck", description="Check a player's forehead kiss total.")
    @app_commands.describe(user="Whose kisses should be checked?")
    async def kisscheck(interaction: discord.Interaction, user: discord.Member) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        total = bot.store.get_kiss_total(interaction.guild.id, user.id)
        embed = make_embed_for_check(user.display_name, total)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="kissredeem", description="Redeem head pats using stored kisses.")
    @app_commands.describe(user="Who is redeeming?", head_pats="How many head pats to redeem?")
    async def kissredeem(
        interaction: discord.Interaction,
        user: discord.Member,
        head_pats: app_commands.Range[int, 1, 100],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        total = bot.store.get_kiss_total(interaction.guild.id, user.id)
        cost = head_pats * HEADPAT_COST
        if total < cost:
            await interaction.response.send_message(
                f"{user.mention} does not have enough kisses yet. They need {cost} total kisses to redeem {head_pats} {head_pat_word(head_pats)}, but only have {total}.",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            return
        new_total = bot.store.remove_kisses(interaction.guild.id, user.id, cost)
        embed = make_embed_for_redeem(user.display_name, head_pats, cost, new_total)
        await interaction.response.send_message(
            content=user.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @bot.tree.command(name="kissleaderboard", description="See the server's top forehead kiss earners.")
    async def kissleaderboard(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        results = bot.store.get_leaderboard(interaction.guild.id)
        if not results:
            await interaction.response.send_message("No forehead kisses have been logged yet.")
            return
        lines = [f"**{index}.** <@{user_id}> - {kisses} forehead {kiss_word(kisses)}" for index, (user_id, kisses) in enumerate(results, start=1)]
        embed = discord.Embed(
            title="Forehead Kiss Leaderboard",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    @bot.tree.command(name="kissset", description="Set a player's kiss total manually.")
    @app_commands.describe(user="Who to edit?", total="The new total number of kisses.")
    @app_commands.default_permissions(manage_guild=True)
    async def kissset(
        interaction: discord.Interaction,
        user: discord.Member,
        total: app_commands.Range[int, 0, 100000],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        actor = interaction.user
        if not isinstance(actor, discord.Member) or not actor.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server to use this command.", ephemeral=True)
            return
        bot.store.set_kiss_total(interaction.guild.id, user.id, total)
        await interaction.response.send_message(
            f"Set {user.mention}'s forehead kiss total to **{total}**.",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    return bot


if __name__ == "__main__":
    token = get_token()
    if token is None:
        print("DISCORD_BOT_TOKEN environment variable is not set.")
        exit(1)
    bot = build_bot()
    bot.run(token)</content>
<parameter name="filePath">/workspaces/kiss.bot/kissbot.py
