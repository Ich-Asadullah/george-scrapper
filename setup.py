from setuptools import setup

APP = ['main.py']  # Replace with your script's filename
OPTIONS = {
    'argv_emulation': True,
    'includes': ['tkinter', 'bs4', 'requests', 'aiohttp', "asyncio", "time", "json", "urllib", "pathlib", "re"],
    'packages': ['bs4', 'requests', 'aiohttp', "Modules"],
    'plist': {
        'CFBundleName': 'Pitzl Edelrid Scraper',
        'CFBundleDisplayName': 'Pitzl Edelrid Scraper',
        'CFBundleIdentifier': 'com.Asad.yourapp',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
    }
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
