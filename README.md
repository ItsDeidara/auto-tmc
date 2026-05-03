# AutoTMC - Automated TMC Installer & Launcher

A Python-based desktop application that automates the installation and management of TMC releases. Features a modern GUI built with CustomTkinter for easy interaction.

## Features

- **Automated Release Management**: Automatically fetch and display the latest TMC releases from GitHub
- **ROM Installation**: Manage ROM installations with verification and tracking
- **Auto-Update Checking**: Optional automatic update checks at configurable intervals
- **Settings Management**: Persistent configuration stored locally
- **Modern UI**: Clean, dark-themed desktop interface with multiple tabs
- **Database Tracking**: SQLite database for tracking installed versions and ROMs

## System Requirements

- **Python 3.14+**
- **Windows, macOS, or Linux**
- **200MB+ disk space** for the application and dependencies

## Python Installation

### Windows
1. Download Python 3.14 from [python.org](https://python.org)
2. Run the installer
3. Check "Add Python to PATH" during installation
4. Verify with: `python --version`

### macOS
```bash
# Using Homebrew (recommended)
brew install python@3.14

# Or download from python.org
```

### Linux
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.14 python3.14-venv

# Fedora/CentOS
sudo dnf install python3.14

# Arch Linux
sudo pacman -S python
```

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/ItsDeidara/auto-tmc.git
cd auto-tmc
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

**Dependencies:**
- `customtkinter>=5.2.2` - Modern GUI framework
- `requests>=2.31.0` - HTTP library for GitHub API
- `Pillow>=10.0.0` - Image processing
- `pyinstaller>=6.0.0` - Executable packaging (for developers)

## Running the Application

```bash
python main.py
```

## Configuration

Configuration is automatically created and managed in:
- **Windows**: `%APPDATA%\AutoTMC\config.json`
- **macOS/Linux**: `~/.AutoTMC/config.json`

## Usage

### Home Tab
- View installation status
- Start installations
- Monitor current version

### Releases Tab
- Browse available TMC releases
- Check release notes
- Download and install specific versions

### Settings Tab
- Configure installation directory
- Set ROM path
- Enable/disable auto-update checks
- Adjust update check interval
- Change application theme

## GitHub Integration

The application connects to the TMC GitHub repository (`999sian/tmc`) to:
- Fetch available releases
- Download release assets
- Verify file integrity with SHA256 checksums
- Display release information and changelogs

### Optional: GitHub Token

You can provide a GitHub personal access token in settings to increase API rate limits. This is optional but recommended for frequent use.

## Troubleshooting

### Application Won't Start
- Check that Python 3.14+ is installed: `python --version`
- Verify all dependencies are installed: `pip install -r requirements.txt`
- Check `error.log` for detailed error messages

### GUI Doesn't Display
- Ensure your display server is running (for headless systems)
- Try updating CustomTkinter: `pip install --upgrade customtkinter`

### Network Issues
- Verify internet connection
- Check if GitHub API is accessible
- Try again in a few moments (API rate limiting)

### Configuration Issues
- Delete the config file to reset to defaults
- Manually edit `config.json` in the AppData folder if needed

## Development

### Building the Executable

To package AutoTMC as a standalone Windows executable, use PyInstaller:

#### 1. Build the EXE
```bash
pyinstaller --onefile --windowed --name="AutoTMC-Windows" --distpath="." main.py
```

**Important:** This places `AutoTMC-Windows.exe` directly in the project root (no `dist/` folder is created).

**Build flags:**
- `--onefile` - Creates a single executable file
- `--windowed` - Removes the console window (GUI-only application)
- `--name="AutoTMC-Windows"` - Names the exe "AutoTMC-Windows.exe"
- `--distpath="."` - Places the exe in the project root (overwrites existing files)
- `--hidden-import=customtkinter` - Include CustomTkinter if the exe crashes on startup

#### 2. Clean Up Build Artifacts
After building, remove the generated `.spec` file:
```bash
# Delete the .spec file (not needed in repo)
rm *.spec
```

#### 3. Locate the Executable
The compiled exe will be in: `AutoTMC-Windows.exe` (project root)

#### Testing the Built Executable
```bash
.\AutoTMC-Windows.exe
```

#### Build Notes
- The first build takes longer as PyInstaller analyzes all dependencies
- Subsequent builds are faster
- **No `dist/` folder is created** - the exe is placed directly in the project root
- **Delete `.spec` files after building** - they are not needed in the repository
- The exe is placed directly in the project root and will overwrite any existing `AutoTMC-Windows.exe`
- The `build/` directory can be safely deleted between builds

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

See LICENSE file in the repository for details.

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review `error.log` for debugging information

## Credits

AutoTMC is designed to work with the TMC project (https://github.com/999sian/tmc).

**Version**: 1.0.0  
**Last Updated**: May 2026