from setuptools import setup

setup(name='factorio_discord_map_preview_bot',
      version='0.0',
      author='Zulan',
      python_requires=">=3.5",
      packages=['factorio_discord_map_preview_bot'],
      scripts=[],
      install_requires=['discord.py', 'click', 'click_log'],
      entry_points='''
        [console_scripts]
        factorio_discord_map_preview_bot=factorio_discord_map_preview_bot:main
      ''')
