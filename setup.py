from setuptools import setup

setup(name='factorio-discord-map-preview-bot',
      version='0.0',
      author='Zulan',
      python_requires=">=3.5",
      packages=['factorio_discord_map_preview_bot'],
      scripts=[],
      install_requires=['discord.py', 'click', 'click_log'],
      entry_points='''
        [console_scripts]
        factorio-discord-map-preview-bot=factorio_discord_map_preview_bot:cli
      ''')
