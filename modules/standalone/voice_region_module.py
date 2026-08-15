import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, Optional
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis
from constants.strings import BotStrings

class VoiceRegionModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="voice-region", description=BotStrings.VOICE_REGION_CMD_DESC)
    @app_commands.describe(
        region=BotStrings.VOICE_REGION_PARAM_DESC
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def voice_region(
        self, 
        interaction: discord.Interaction, 
        region: Literal["Automatic", "russia", "rotterdam", "hong-kong", "brazil", "sydney", "singapore", "us-central", "us-east"]
    ):
        """Сменяет регион (RTC Region) для всех голосовых каналов сервера."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_GUILD_ONLY}")
            return

        # Проверка прав бота
        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_NO_PERMS}")
            return

        # 'Automatic' в discord.py соответствует значению None
        rtc_value = None if region == "Automatic" else region
        
        updated_count = 0
        errors_count = 0

        for channel in guild.voice_channels:
            try:
                # Пропускаем, если регион уже совпадает
                if str(channel.rtc_region) == str(rtc_value):
                    continue

                await channel.edit(rtc_region=rtc_value)
                updated_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                errors_count += 1

        status_display = BotStrings.VOICE_REGION_AUTOMATIC if region == "Automatic" else f"'{region}'"
        
        result_msg = f"{Emojis.SUCCESS} " + BotStrings.VOICE_REGION_SUCCESS.format(status=status_display, updated=updated_count)
        if errors_count > 0:
            result_msg += BotStrings.VOICE_REGION_ERRORS.format(errors=errors_count)
            
        await interaction.followup.send(result_msg)
        
        log_msg = (
            f"Администратор {interaction.user} сменил регион всех каналов на {status_display} "
            f"на сервере {guild.name}. Обновлено каналов: {updated_count}."
        )
        await send_to_any_log("info", log_msg, emoji=LogEmojis.INFO)

    @commands.command(name="voice-region", aliases=["voice_region", "регион", "сменить_регион"])
    @commands.has_permissions(manage_channels=True)
    async def voice_region_cmd(self, ctx: commands.Context, region: str = "Automatic"):
        """Префиксная команда смены региона голосовых каналов."""
        guild = ctx.guild
        if not guild:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_GUILD_ONLY}")
            return

        if not guild.me.guild_permissions.manage_channels:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_NO_PERMS}")
            return

        clean_region = region.strip()
        rtc_value = None if clean_region.lower() in ["automatic", "auto", "авто", "автоматически", "none"] else clean_region

        updated_count = 0
        errors_count = 0

        for channel in guild.voice_channels:
            try:
                if str(channel.rtc_region) == str(rtc_value):
                    continue
                await channel.edit(rtc_region=rtc_value)
                updated_count += 1
                await asyncio.sleep(0.5)
            except Exception:
                errors_count += 1

        status_display = BotStrings.VOICE_REGION_AUTOMATIC if rtc_value is None else f"'{rtc_value}'"
        result_msg = f"{Emojis.SUCCESS} " + BotStrings.VOICE_REGION_SUCCESS.format(status=status_display, updated=updated_count)
        if errors_count > 0:
            result_msg += BotStrings.VOICE_REGION_ERRORS.format(errors=errors_count)

        await ctx.send(result_msg)

    @commands.command(name="voice-list", aliases=["voice_list", "регионы", "список_регионов"])
    async def voice_list_cmd(self, ctx: commands.Context):
        """Префиксная команда вывода списка голосовых каналов и их регионов."""
        guild = ctx.guild
        if not guild:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_GUILD_ONLY}")
            return

        lines = []
        channels = sorted(guild.voice_channels, key=lambda c: c.position)
        for channel in channels:
            region = str(channel.rtc_region) if channel.rtc_region else "Automatic"
            lines.append(f"{Emojis.SPEAKER} **{channel.name}** — `{region}`")

        if not lines:
            await ctx.send(BotStrings.VOICE_ERR_NO_CHANNELS)
            return

        header = f"### {Emojis.STATUS} {BotStrings.VOICE_LIST_HEADER.format(guild=guild.name)}\n"
        full_output = header + "\n".join(lines)
        if len(full_output) > 2000:
            current_message = header
            for line in lines:
                if len(current_message) + len(line) + 2 > 2000:
                    await ctx.send(current_message)
                    current_message = ""
                current_message += line + "\n"
            if current_message:
                await ctx.send(current_message)
        else:
            await ctx.send(full_output)

    @app_commands.command(name="voice-list", description=BotStrings.VOICE_LIST_CMD_DESC)
    async def voice_list(self, interaction: discord.Interaction):
        """Выводит список каналов и их RTC регионов."""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.VOICE_ERR_GUILD_ONLY}")
            return

        lines = []
        # Сортируем по позиции для удобства
        channels = sorted(guild.voice_channels, key=lambda c: c.position)
        
        for channel in channels:
            region = str(channel.rtc_region) if channel.rtc_region else "Automatic"
            lines.append(f"{Emojis.SPEAKER} **{channel.name}** — `{region}`")

        if not lines:
            await interaction.followup.send(BotStrings.VOICE_ERR_NO_CHANNELS)
            return

        header = f"### {Emojis.STATUS} {BotStrings.VOICE_LIST_HEADER.format(guild=guild.name)}\n"
        full_output = header + "\n".join(lines)
        
        # Если список очень длинный, разбиваем на части
        if len(full_output) > 2000:
            current_message = header
            for line in lines:
                if len(current_message) + len(line) + 2 > 2000:
                    await interaction.followup.send(current_message)
                    current_message = ""
                current_message += line + "\n"
            if current_message:
                await interaction.followup.send(current_message)
        else:
            await interaction.followup.send(full_output)

async def setup(bot):
    await bot.add_cog(VoiceRegionModule(bot))
