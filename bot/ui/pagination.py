from __future__ import annotations

import discord


class Paginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.previous.disabled = self.index <= 0
        self.next.disabled = self.index >= len(self.pages) - 1
        self.counter.label = f"{self.index + 1}/{len(self.pages)}"

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)
