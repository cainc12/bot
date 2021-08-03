from collections import defaultdict
import typing
from discord.ext import commands
from ink.core import squidcommand, Context
import discord
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color
from wand.font import Font
from io import BytesIO
import aiohttp
from wand.drawing import Drawing
import random
from copy import copy
from .player import Player, get_level_from_xp, lvls_xp
from .config import DEFAULT_XP_COOLDOWN, DEFAULT_XP_REWARD_RANGE


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open(__file__[:-6] + "template.png", "rb") as fp:
            self.template = fp.read()

        with open(__file__[:-6] + "mask.png", "rb") as fp:
            self.mask = fp.read()

        self.xp_cooldown = self.bot.config.get("xp-cooldown", DEFAULT_XP_COOLDOWN)
        self.xp_reward_range = tuple(
            self.bot.config.get("xp-reward-range", DEFAULT_XP_REWARD_RANGE)
        )

        self.players = defaultdict(dict)
        self._get_level_xp = lambda n: 5 * (n ** 2) + 50 * n + 100

        self.font = Font(
            path=__file__[:-6] + "Aquire.otf", color=Color("white"), antialias=True
        )

    def get_player(self, member: discord.Object):
        cached_player = self.players.get(member.id)
        if cached_player:
            return cached_player
        player = Player(member, member.guild, self.bot.sync_redis)
        self.players[member.id] = player

        return player

    def get_player_info(self, member):
        player = self.get_player(member)
        if player.xp == 0:
            return None
        player_total_xp = player.xp
        player_lvl = player.lvl
        x = 0
        for l in range(0, int(player_lvl)):
            x += self._get_level_xp(l)
        remaining_xp = int(player_total_xp - x)
        level_xp = self._get_level_xp(player_lvl)
        players = self.bot.sync_redis.zcount("leaderboard", 0, 1e9)
        player_rank = player.rank

        return {
            "total_xp": player_total_xp,
            "lvl": player_lvl,
            "remaining_xp": remaining_xp,
            "level_xp": level_xp,
            "rank": player_rank,
            "total_players": players,
        }

    @commands.Cog.listener("level_up")
    async def levelup_tracker(
        self, context: Context, player: Player, og_lvl: int, new_level: int
    ):
        print(f"{context.author.name} has just leveled up from {og_lvl} to {new_level}")

    @commands.Cog.listener()
    async def on_context(self, context: Context) -> None:
        if context.author.bot:
            return

        author: discord.Member = context.author  # for future object-changing compat

        key = f"Leveling:cd:{author.id}"
        if await self.bot.redis.exists(key):
            return
        else:
            await self.bot.redis.set(key, 1, expire=self.xp_cooldown)

        player = self.get_player(context.author)

        og_lvl = copy(player.lvl)

        amn = random.randint(*self.xp_reward_range)

        player.xp += amn

        print(f"Gave {author.name} {amn} xp")
        if player.lvl != og_lvl:
            self.bot.dispatch("level_up", context, player, og_lvl, player.lvl)

    @squidcommand("rank", aliases=["r"])
    @commands.bot_has_guild_permissions(attach_files=True)
    async def rank(self, ctx: Context, member: discord.Member = None):
        """View the rank of yourself or a member

        Arguments:
            member (discord.Member, optional): The member you want to view the rank of. Defaults to None.

        Requires:
            [ attach files ]
        """
        member = member or ctx.author
        info = self.get_player_info(member)
        if member.bot:
            raise commands.CommandError("Bot's don't have profiles")
        with Drawing() as draw:
            draw.fill_color = Color("pink")
            draw.fill_opacity = 0.8
            width = int(info["remaining_xp"] / info["level_xp"] * 600)
            draw.rectangle(left=300, top=215, width=width, height=50, radius=20)

            # name
            # draw.font = self.font
            # draw.text(300, 500, f"{ctx.author.name} #{ctx.author.tag}")
            with Image(blob=self.template) as image:
                url = str(member.avatar.replace(static_format="png", size=256)).replace(
                    "gif", "png"
                )
                print(url)
                async with self.bot.session.get(url) as req:
                    with Image(blob=await req.read()) as img:
                        img.resize(256, 256)
                        with Image(blob=self.mask) as mask:

                            img.composite_channel("all_channels", mask, "screen")

                            img.transparent_color(
                                Color("white"), alpha=0, fuzz=int(65535 * 0.03)
                            )
                        image.composite(img, left=20, top=20)

                draw(image)
                img_data = image.make_blob("png")

        yield discord.File(fp=BytesIO(img_data), filename="jaydumb.png")  # thanks jay
