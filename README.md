# YouTube Shorts Bot Manager

A professional GUI application for automating YouTube Shorts creation from Reddit content across multiple channels.

## Features

- **Multi-Channel Management**: Handle multiple YouTube channels with individual profiles
- **Smart Video Processing**: Automatic video conversion to YouTube Shorts format (1080x1920)
- **Reddit Integration**: Fetch content from specified subreddits with multiple sorting options
- **Audio Detection**: Smart background music addition based on audio presence
- **Modern GUI**: Clean, professional interface built with tkinter/CustomTkinter
- **Upload History**: Track daily upload limits and processing history
- **Startup Management**: Run channels automatically on Windows startup
- **Real-time Monitoring**: Live logs and progress tracking

## Quick Start

### Prerequisites

- Python 3.8 or higher
- YouTube Data API v3 credentials (`client_secrets.json`)
- Reddit API credentials (for PRAW)

### Installation

1. Clone this repository:
```bash
git clone https://github.com/danielbconley/Multi-Channel-Youtube-Automation-Bot
cd youtube-shorts-bot
```

2. Create and activate a virtual environment (recommended):
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

**Alternative**: If you prefer not to use a virtual environment, you can skip step 2 and install packages globally. However, using a virtual environment is strongly recommended to avoid package conflicts.

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up credentials:
   - Place your `client_secrets.json` file in the project directory
   - Configure Reddit credentials in `config.py`

5. Run the application:
```bash
python gui_manager.py
```

**Note**: If using a virtual environment, always activate it (`venv\Scripts\activate` on Windows or `source venv/bin/activate` on macOS/Linux) before running the application. If you installed packages globally, you can run the application directly.

## Configuration

### Channel Profiles

Create channel profiles through the GUI with:
- **Label**: Display name for the channel
- **Subreddit**: Reddit source (e.g., "dashcam")
- **YouTube Token**: OAuth token file path
- **Music Directory**: Background music folder
- **Sample Titles**: Video title templates
- **Hashtags**: Channel-specific hashtags
- **Font Settings**: Text overlay customization

### Music Integration

- Place music files in designated folders (MP3, M4A, WAV supported)
- Configure volume levels (affects background music only)
- Smart mode automatically detects silent videos

## Usage

### Processing Videos

1. **Single Channel**: Select a channel and click "Process Selected Channel"
2. **Batch Processing**: Use "Process All Channels" for multiple channels
3. **Test Mode**: Use test buttons for private uploads (testing)

### Startup Management

- Enable channels for automatic startup processing
- Windows startup integration via batch files
- Daily upload limit enforcement

## Project Structure

```
youtube-shorts-bot/
├── gui_manager.py          # Main GUI application
├── process_videos.py       # Video processing engine
├── audio_detection.py      # Audio analysis module
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
├── .gitignore             # Git ignore rules
├── profiles.json          # Channel configurations (not in repo)
├── client_secrets.json    # YouTube API credentials (not in repo)
├── tokens/                # OAuth tokens (not in repo)
├── processed/             # Processing history (not in repo)
├── music/                 # Background music files (not in repo)
└── out/                   # Generated videos (not in repo)
```

## Technical Details

### Video Processing
- Converts horizontal videos to vertical (1080x1920) format
- Smart cropping with configurable zoom levels
- Text overlay with custom fonts and positioning
- Background music mixing with volume control

### API Integration
- YouTube Data API v3 for uploads
- Reddit API (PRAW) for content fetching
- OAuth 2.0 authentication flow

### Safety Features
- UTF-8 encoding error handling
- Process abortion mechanisms
- Daily upload limit enforcement
- Duplicate content detection

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Disclaimer

This tool is for educational purposes. Ensure you:
- Comply with YouTube's Terms of Service
- Respect Reddit's API guidelines
- Have proper rights to any music used
- Follow content creation best practices

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Common Issues
- **Encoding Errors**: The system automatically handles UTF-8 issues
- **API Limits**: Daily upload limits are enforced automatically
- **Missing Dependencies**: Install all requirements from `requirements.txt`

### Support
- Check the logs tab for detailed error information
- Ensure all API credentials are properly configured
- Verify file paths and permissions

---

**Note**: Remember to keep your API credentials secure and never commit them to version control!


