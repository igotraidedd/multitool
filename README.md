# tuff ash multi tool made by me

An all-in-one Windows system toolkit with 130+ tools for system optimization, network diagnostics, OSINT, security auditing, and more — all from a single terminal interface.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)

## Features

The toolkit is organized into **6 tabs**:

### Tools (34 tools)
System management essentials — junk file cleaner, process manager, startup manager, network tools, registry cleaner, disk optimizer, system repair, event log viewer, firewall & open ports, memory optimizer, live performance monitor, system info, environment variable editor, WiFi manager, hosts file editor, bandwidth monitor, network mapper, visual traceroute, ping sweep, Wake-on-LAN, and more.

### Optimize (33 tools)
Performance tuning — full one-click optimization, power plan manager, game & performance optimizer, visual effects toggle, CPU priority tweaks, GPU optimization, SSD/HDD tweaks, network latency (gaming), telemetry & privacy disabler, hibernation & sleep settings, advanced registry tweaks, boot analysis, driver health check, Windows Defender tuning, DNS optimizer, RAM optimizer, Windows debloater, shader cache manager, and more.

### OSINT (32 tools)
Open-source intelligence — IP/domain lookup, DNS record lookup, reverse IP, WHOIS, subdomain finder, port scanner with banner grabbing, breach/leak checker, Google dorking helper, URL analyzer, MAC address lookup, Tor/VPN/proxy detector, website fingerprinter, email header analyzer, EXIF metadata extractor, phone number lookup, SSL certificate checker, geolocation tracker, username search across 37+ platforms, social media deep scraper, dark web mention checker, and more.

### Security (11 tools)
Security auditing — hash cracker, directory bruteforcer, subdomain takeover check, header security analyzer, CVE lookup, privacy audit, tracker blocker, browser data cleaner, DNS leak test, VPN checker, webcam & mic monitor.

### Utilities (21 tools)
Developer & daily-use tools — text utilities, JSON/XML formatter, password generator, hash generator, base converter, timestamp converter, calculator, unit converter, file search, duplicate file finder, bulk file renamer, stopwatch & timer, color picker, diff tool, file encryptor, secure file shredder, archive manager, and more.

### Fun (6 tools)
ASCII art generator, matrix rain, system stats flex, typing speed test, number guessing game, rock paper scissors.

## Requirements

- **OS:** Windows 10 / 11
- **Python:** 3.8+
- **Dependencies:** `rich`, `psutil` (auto-installed on first run)

## Installation

```bash
pip install rich psutil
```

## Usage

```bash
python "raideds tool.py"
```

On launch you'll be prompted to elevate to Administrator — many tools (registry tweaks, service management, system repair) require admin privileges, but the toolkit works in normal user mode too.

### Navigation

| Key | Action |
|-----|--------|
| Number | Select a tool |
| `<` / `>` or tab name | Switch tabs |
| `/` | Search all tools |
| `F` | View favorites |
| `f<number>` | Toggle a tool as favorite |
| `0` / `q` | Quit |

## Configuration

Settings are stored in `%APPDATA%\raideds-tool\config.json` and include:
- API keys (Shodan, HIBP)
- Favorite tools
- Recent tool history
- Theme preferences

## Notes

- Some OSINT features use free public APIs (ip-api.com, crt.sh, etc.) and may be rate-limited.
- Breach checking via HaveIBeenPwned requires a free API key from [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key).
- For full EXIF metadata extraction, install [ExifTool](https://exiftool.org).
- Packet sniffing features require [Npcap](https://npcap.com) and the `scapy` package.
