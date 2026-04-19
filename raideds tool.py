"""
╔══════════════════════════════════════╗
║   raideds tool                        ║
║   Run: python "raideds tool.py"     ║
║   Requires: pip install rich psutil  ║
╚══════════════════════════════════════╝
"""

import os, sys, shutil, subprocess, socket, time, ctypes, platform, winreg, gc, hashlib, secrets, string, urllib.request, urllib.parse, ssl, json, re, random
from pathlib import Path
from datetime import datetime
import threading

for pkg in ("rich", "psutil"):
    try:
        __import__(pkg)
    except ImportError:
        print(f"Installing {pkg}...") 
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=True)

from rich.console import Console, Group
from rich.table   import Table
from rich.panel   import Panel
from rich.text    import Text
from rich.prompt  import Confirm, Prompt
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.columns import Columns
from rich.live    import Live
from rich         import box
import psutil

console  = Console()
ctypes.windll.kernel32.SetConsoleTitleW("raideds tool")
IS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
HOME     = Path(os.environ.get("USERPROFILE", Path.home()))
LAD      = Path(os.environ.get("LOCALAPPDATA", ""))
APPDATA  = Path(os.environ.get("APPDATA", ""))

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG / SETTINGS SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
CONFIG_DIR  = Path(os.environ.get("APPDATA", "")) / "raideds-tool"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_CONFIG = {
    "api_keys": {"shodan": "", "hibp": ""},
    "favorites": [],
    "recent": [],
    "max_recent": 10,
    "theme": "default",
    "verbose_menus": False,
}

def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = {**DEFAULT_CONFIG, **saved}
            cfg["api_keys"] = {**DEFAULT_CONFIG["api_keys"], **saved.get("api_keys", {})}
            return cfg
    except (json.JSONDecodeError, OSError):
        pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass

def get_setting(key, default=None):
    return CONFIG.get(key, default)

def set_setting(key, value):
    CONFIG[key] = value
    save_config(CONFIG)

def add_recent(tool_name):
    recent = CONFIG.get("recent", [])
    if tool_name in recent:
        recent.remove(tool_name)
    recent.insert(0, tool_name)
    CONFIG["recent"] = recent[:CONFIG.get("max_recent", 10)]
    save_config(CONFIG)

def toggle_favorite(tool_name):
    favs = CONFIG.get("favorites", [])
    if tool_name in favs:
        favs.remove(tool_name)
    else:
        favs.append(tool_name)
    CONFIG["favorites"] = favs
    save_config(CONFIG)

def is_favorite(tool_name):
    return tool_name in CONFIG.get("favorites", [])

CONFIG = load_config()

# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def validate_ip(ip):
    try:
        parts = ip.strip().split(".")
        if len(parts) != 4: return False
        return all(0 <= int(p) <= 255 for p in parts)
    except (ValueError, AttributeError):
        return False

def validate_port(port):
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False

def validate_domain(domain):
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain.strip()))

def validate_url(url):
    try:
        parsed = urllib.parse.urlparse(url.strip())
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))

def safe_run(func):
    """Decorator that wraps tool functions with consistent error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            console.print(f"\n  [red]Error: {e}[/red]")
            pause()
    wrapper.__name__ = func.__name__
    return wrapper


def fmt_bytes(b):
    if not b: return "0 B"
    for u in ["B","KB","MB","GB","TB"]:
        if abs(b) < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"

def pct_bar(pct, width=28):
    filled = int(pct * width / 100)
    col    = "red" if pct >= 85 else "yellow" if pct >= 60 else "green"
    return f"[{col}]{'█'*filled}[/{col}][dim]{'░'*(width-filled)}[/dim] {pct:.0f}%"

def header(title, hint=""):
    console.clear()
    adm = "[bold green] ADMIN [/bold green]" if IS_ADMIN else "[bold yellow] not admin [/bold yellow]"
    console.print(Panel(
        f"[bold cyan]raideds tool 🤑[/bold cyan]  {adm}\n"
        f"[dim]{platform.node()}  •  Windows {platform.version()[:30]}[/dim]",
        style="cyan", padding=(0,2)
    ))
    console.print(f"\n  [bold white]{title}[/bold white]" +
                  (f"  [dim]│  {hint}[/dim]" if hint else ""))
    console.print("  [dim]" + "─"*56 + "[/dim]\n")

def pause(msg="Press ENTER to go back"):
    console.print(f"\n  [dim]{msg}...[/dim]")
    input()

def ask(prompt, default=""):
    try:
        return Prompt.ask(f"  [cyan]{prompt}[/cyan]", default=default)
    except (KeyboardInterrupt, EOFError):
        return default

def confirm(msg):
    try:
        return Confirm.ask(f"  [yellow]{msg}[/yellow]")
    except (KeyboardInterrupt, EOFError):
        return False

def numbered_menu(title_or_options, options=None, hint=""):
    """Simple numbered pick menu. Returns index or -1."""
    if options is None and isinstance(title_or_options, list):
        options = title_or_options
        title = None
    else:
        title = title_or_options
    while True:
        if title is not None:
            header(title, hint)
        for i, opt in enumerate(options, 1):
            console.print(f"  [bold cyan]{i:>2}[/bold cyan]  {opt}")
        console.print(f"  [bold cyan] 0[/bold cyan]  [dim]Back[/dim]\n")
        raw = ask("Pick").strip()
        if raw in ("0","b","q",""):
            return -1
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1

def run_ps(cmd, timeout=30):
    """Run a PowerShell command and return stdout."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception as e:
        return str(e)

def run_cmd(args, timeout=15):
    try:
        subprocess.run(args, capture_output=True, timeout=timeout)
        return True
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        return False


JUNK_TARGETS = [
    ("User Temp (%TEMP%)",          Path(os.environ.get("TEMP","")),                            False),
    ("Windows Temp",                Path("C:/Windows/Temp"),                                    True ),
    ("Crash Dumps",                 LAD / "CrashDumps",                                         False),
    ("WER Reports (user)",          LAD / "Microsoft/Windows/WER/ReportArchive",                False),
    ("WER Reports (system)",        Path("C:/ProgramData/Microsoft/Windows/WER/ReportArchive"), True ),
    ("Thumbnail Cache",             LAD / "Microsoft/Windows/Explorer",                         False),
    ("Icon Cache",                  LAD,                                                         False),
    ("Windows Update Cache",        Path("C:/Windows/SoftwareDistribution/Download"),           True ),
    ("Chrome Cache",                LAD / "Google/Chrome/User Data/Default/Cache",              False),
    ("Chrome GPU Cache",            LAD / "Google/Chrome/User Data/Default/GPUCache",           False),
    ("Edge Cache",                  LAD / "Microsoft/Edge/User Data/Default/Cache",             False),
    ("Firefox Cache",               APPDATA / "Mozilla/Firefox/Profiles",                       False),
    ("Brave Cache",                 LAD / "BraveSoftware/Brave-Browser/User Data/Default/Cache",False),
    ("Prefetch Files",              Path("C:/Windows/Prefetch"),                                True ),
    ("DNS Cache (flush)",           None,                                                        False),
    ("Recycle Bin",                 None,                                                        False),
    ("Delivery Optimization Cache", Path("C:/Windows/SoftwareDistribution/DeliveryOptimization"),True),
    ("DirectX Shader Cache",        LAD / "D3DSCache",                                          False),
    ("Windows Installer Patch Cache",Path("C:/Windows/Installer/$PatchCache$"),                 True ),
    ("Event Logs",                  None,                                                        True ),
]

def folder_size(p):
    total = 0
    try:
        for f in Path(p).rglob("*"):
            try:
                if f.is_file(): total += f.stat().st_size
            except Exception:
                pass
    except Exception:
        pass
    return total

def clean_path(p, icon_cache=False):
    freed = 0
    try:
        for item in Path(p).iterdir():
            try:
                if icon_cache and "iconcache" not in item.name.lower(): continue
                if item.is_file() or item.is_symlink():
                    freed += item.stat().st_size
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    freed += folder_size(item)
                    shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass
    return freed

def junk_cleaner():
    selected = set(i for i,(l,p,na) in enumerate(JUNK_TARGETS) if not na)
    cur = 0
    while True:
        header("Junk File Cleaner", "W/S=move  SPACE=toggle  A=all  R=run  B=back")
        for i, (label, path, needs_admin) in enumerate(JUNK_TARGETS):
            chk      = "X" if i in selected else " "
            chk_col  = "green" if i in selected else "dim"
            arrow    = "[yellow]>[/yellow]" if i == cur else " "
            disabled = needs_admin and not IS_ADMIN
            label_col= "dim" if disabled else ("cyan" if i==cur else "white")
            suffix   = "  [dim](admin)[/dim]" if disabled else ""
            console.print(f"  {arrow} [[{chk_col}]{chk}[/{chk_col}]] [{label_col}]{label}[/{label_col}]{suffix}")
        console.print(f"\n  [dim]Selected: {len(selected)}/{len(JUNK_TARGETS)}[/dim]")
        raw = ask("").strip().lower()
        if   raw == "b":  return
        elif raw == "w":  cur = max(0, cur-1)
        elif raw == "s":  cur = min(len(JUNK_TARGETS)-1, cur+1)
        elif raw == " " or raw == "space":
            if not (JUNK_TARGETS[cur][2] and not IS_ADMIN):
                selected ^= {cur}
        elif raw == "a":
            eligible = {i for i,(l,p,na) in enumerate(JUNK_TARGETS) if not (na and not IS_ADMIN)}
            selected = eligible if not eligible.issubset(selected) else set()
        elif raw == "r":
            if not selected: continue
            break

    header("Cleaning...")
    total = 0
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
        task = prog.add_task("", total=len(selected))
        for i in sorted(selected):
            label, path, _ = JUNK_TARGETS[i]
            prog.update(task, description=f"{label:<35}")
            if label == "DNS Cache (flush)":
                run_cmd(["ipconfig","/flushdns"])
            elif label == "Recycle Bin":
                try: ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 1)
                except Exception:
                    pass
            elif label == "Icon Cache":
                total += clean_path(path, icon_cache=True)
            elif label == "Event Logs":
                run_ps("wevtutil el | ForEach-Object { wevtutil cl $_ }")
            elif path and Path(path).exists():
                total += clean_path(path)
            prog.advance(task)

    console.print(f"\n  [bold green]✓ Done!  {fmt_bytes(total)} freed.[/bold green]")
    pause()


def process_manager():
    sort_by = "cpu"
    while True:
        header("Process Manager", "R=refresh  K=kill  C=sort CPU  M=sort RAM  B=back")
        try:
            procs = []
            for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","status","username"]):
                try:
                    procs.append(p.info)
                except Exception:
                    pass
            time.sleep(0.3)
            for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","status"]):
                try:
                    for pr in procs:
                        if pr["pid"] == p.info["pid"]:
                            pr["cpu_percent"] = p.info["cpu_percent"]
                except Exception:
                    pass

            key = "cpu_percent" if sort_by == "cpu" else lambda x: x.get("memory_info").rss if x.get("memory_info") else 0
            if sort_by == "cpu":
                procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
            else:
                procs.sort(key=lambda x: x.get("memory_info").rss if x.get("memory_info") else 0, reverse=True)

            t = Table(box=box.ROUNDED, header_style="bold cyan", expand=True)
            t.add_column("PID",    justify="right", width=7)
            t.add_column("Name",   width=28)
            t.add_column("CPU %",  justify="right", width=7)
            t.add_column("RAM",    justify="right", width=9)
            t.add_column("Status", width=10)
            t.add_column("User",   width=14)
            for p in procs[:28]:
                cpu = p.get("cpu_percent") or 0
                ram = p.get("memory_info").rss if p.get("memory_info") else 0
                cpu_col = "red" if cpu>50 else "yellow" if cpu>15 else "white"
                t.add_row(
                    str(p["pid"]),
                    (p.get("name") or "?")[:27],
                    f"[{cpu_col}]{cpu:.1f}[/{cpu_col}]",
                    fmt_bytes(ram),
                    f"[dim]{p.get('status','?')}[/dim]",
                    f"[dim]{(p.get('username') or '?').split('\\\\')[-1][:13]}[/dim]"
                )
            console.print(t)
            console.print(f"\n  [dim]Sort: [cyan]{sort_by.upper()}[/cyan]   Total: {len(procs)} processes[/dim]")
        except Exception as e:
            console.print(f"  [red]{e}[/red]")

        raw = ask("").strip().lower()
        if   raw == "b": return
        elif raw == "r": continue
        elif raw == "c": sort_by = "cpu"
        elif raw == "m": sort_by = "ram"
        elif raw == "k":
            pid_str = ask("PID to kill")
            if pid_str.isdigit():
                try:
                    proc = psutil.Process(int(pid_str))
                    if confirm(f"Kill {proc.name()} (PID {pid_str})?"):
                        proc.kill()
                        console.print("  [green]Killed.[/green]"); time.sleep(0.6)
                except Exception as e:
                    console.print(f"  [red]{e}[/red]"); time.sleep(1)


def get_startup_items():
    items = []
    paths = [
        (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, sub in paths:
        try:
            key = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    items.append({"name":name,"cmd":val,"src":sub.split("\\")[-1],
                                  "type":"reg","hive":hive,"sub":sub})
                    i += 1
                except OSError: break
            winreg.CloseKey(key)
        except Exception:
            pass
    for sf in [str(APPDATA/r"Microsoft\Windows\Start Menu\Programs\Startup"),
               r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp"]:
        try:
            for f in Path(sf).iterdir():
                if f.is_file():
                    items.append({"name":f.stem,"cmd":str(f),"src":"Folder",
                                  "type":"folder","path":f})
        except Exception:
            pass
    return items

def startup_manager():
    items = get_startup_items()
    cur   = 0
    while True:
        header(f"Startup Manager  ({len(items)} items)", "W/S=move  D=delete  B=back")
        if not items:
            console.print("  [dim]No startup items found.[/dim]"); pause(); return
        t = Table(box=box.SIMPLE, header_style="bold cyan", expand=True)
        t.add_column("", width=3)
        t.add_column("Name",    width=30)
        t.add_column("Source",  width=12)
        t.add_column("Command", width=48)
        for i, item in enumerate(items):
            arrow  = "[yellow]>[/yellow]" if i == cur else " "
            style  = "cyan" if i == cur else "white"
            cmd    = item["cmd"]
            if len(cmd) > 48: cmd = cmd[:45]+"..."
            t.add_row(arrow, f"[{style}]{item['name'][:29]}[/{style}]",
                      f"[dim]{item['src']}[/dim]", f"[dim]{cmd}[/dim]")
        console.print(t)
        raw = ask("").strip().lower()
        if   raw == "b": return
        elif raw == "w": cur = max(0, cur-1)
        elif raw == "s": cur = min(len(items)-1, cur+1)
        elif raw == "d":
            it = items[cur]
            if confirm(f"Remove '{it['name']}' from startup?"):
                try:
                    if it["type"] == "reg":
                        k = winreg.OpenKey(it["hive"], it["sub"], 0, winreg.KEY_WRITE)
                        winreg.DeleteValue(k, it["name"])
                        winreg.CloseKey(k)
                    else:
                        Path(it["path"]).unlink(missing_ok=True)
                    console.print("  [green]Removed.[/green]"); time.sleep(0.6)
                    items = get_startup_items()
                    cur   = min(cur, max(0, len(items)-1))
                except Exception as e:
                    console.print(f"  [red]{e}[/red]"); time.sleep(1)


def network_tools():
    opts = [
        "IP & Adapter Info",
        "Ping Test",
        "Flush DNS",
        "DNS Benchmark  (test multiple servers)",
        "Active Connections",
        "Network Speed Stats",
        "Reset TCP/IP  (Admin)",
        "Reset Winsock  (Admin)",
        "Wi-Fi Password Viewer  (Admin)",
    ]
    while True:
        sel = numbered_menu("Network Tools", opts)
        if sel == -1: return
        header("Network Tools", opts[sel])

        if sel == 0:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Adapter",  width=22)
            t.add_column("IPv4",     width=16)
            t.add_column("MAC",      width=18)
            t.add_column("Speed",    justify="right", width=10)
            t.add_column("Up",       width=6)
            for name, addrs in psutil.net_if_addrs().items():
                stats = psutil.net_if_stats().get(name)
                ip  = next((a.address for a in addrs if a.family == socket.AF_INET), "")
                mac = next((a.address for a in addrs if a.family == psutil.AF_LINK), "")
                if not ip: continue
                speed  = f"{stats.speed} Mbps" if stats and stats.speed else "?"
                status = "[green]UP[/green]" if stats and stats.isup else "[red]DN[/red]"
                t.add_row(name[:21], ip, mac, speed, status)
            console.print(t)
            try:
                pub = subprocess.run(["curl","-s","--max-time","4","https://api.ipify.org"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
                console.print(f"\n  Public IP: [cyan]{pub}[/cyan]")
            except Exception:
                pass

        elif sel == 1:
            host = ask("Host to ping", "google.com")
            times = []
            for _ in range(5):
                try:
                    t0   = time.time()
                    s    = socket.create_connection((host, 80), timeout=3)
                    ms   = (time.time()-t0)*1000
                    s.close()
                    times.append(ms)
                    col = "green" if ms<50 else "yellow" if ms<150 else "red"
                    console.print(f"    Reply [{col}]{ms:.1f}ms[/{col}]")
                except:
                    console.print("    [red]Timeout[/red]")
                time.sleep(0.4)
            if times:
                console.print(f"\n  Avg [cyan]{sum(times)/len(times):.1f}ms[/cyan]  "
                              f"Min [green]{min(times):.1f}ms[/green]  "
                              f"Max [red]{max(times):.1f}ms[/red]")

        elif sel == 2:
            run_cmd(["ipconfig","/flushdns"])
            console.print("  [green]DNS flushed.[/green]")

        elif sel == 3:
            servers = {
                "Google":      "8.8.8.8",
                "Cloudflare":  "1.1.1.1",
                "OpenDNS":     "208.67.222.222",
                "Quad9":       "9.9.9.9",
                "Comodo":      "8.26.56.26",
            }
            console.print("  [yellow]Benchmarking DNS servers...[/yellow]\n")
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Server",    width=14)
            t.add_column("IP",        width=16)
            t.add_column("Avg (ms)",  justify="right", width=10)
            t.add_column("Rating",    width=10)
            results = []
            for name, ip in servers.items():
                times = []
                for _ in range(3):
                    try:
                        t0 = time.time()
                        s  = socket.create_connection((ip, 53), timeout=2)
                        times.append((time.time()-t0)*1000)
                        s.close()
                    except: times.append(9999)
                avg = sum(times)/len(times)
                results.append((name, ip, avg))
            results.sort(key=lambda x: x[2])
            for i, (name, ip, avg) in enumerate(results):
                col    = "green" if i==0 else "yellow" if i<=2 else "red"
                rating = "⭐ BEST" if i==0 else "Good" if i<=2 else "Slow"
                t.add_row(name, ip, f"[{col}]{avg:.1f}[/{col}]", f"[{col}]{rating}[/{col}]")
            console.print(t)
            console.print(f"\n  [dim]Tip: Set your DNS to [cyan]{results[0][1]}[/cyan] ({results[0][0]}) for best speed.[/dim]")

        elif sel == 4:
            t = Table(box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Local",   width=24)
            t.add_column("Remote",  width=24)
            t.add_column("State",   width=12)
            t.add_column("Process", width=16)
            shown = 0
            for c in psutil.net_connections("inet"):
                if c.status == "ESTABLISHED":
                    try: pname = psutil.Process(c.pid).name() if c.pid else "?"
                    except: pname = "?"
                    la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                    ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                    t.add_row(la, ra, "[green]ESTABLISHED[/green]", pname[:15])
                    shown += 1
                    if shown >= 20: break
            console.print(t)

        elif sel == 5:
            io1 = psutil.net_io_counters()
            console.print("  [yellow]Sampling 2 seconds...[/yellow]")
            time.sleep(2)
            io2  = psutil.net_io_counters()
            sent = (io2.bytes_sent - io1.bytes_sent) / 2
            recv = (io2.bytes_recv - io1.bytes_recv) / 2
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Metric",    width=24)
            t.add_column("Value",     justify="right", width=16)
            t.add_row("Upload speed",      f"[cyan]{fmt_bytes(sent)}/s[/cyan]")
            t.add_row("Download speed",    f"[green]{fmt_bytes(recv)}/s[/green]")
            t.add_row("Total sent",        fmt_bytes(io2.bytes_sent))
            t.add_row("Total received",    fmt_bytes(io2.bytes_recv))
            t.add_row("Packets sent",      str(io2.packets_sent))
            t.add_row("Packets received",  str(io2.packets_recv))
            t.add_row("Errors in",         f"[red]{io2.errin}[/red]")
            t.add_row("Errors out",        f"[red]{io2.errout}[/red]")
            console.print(t)

        elif sel == 6:
            if IS_ADMIN: run_cmd(["netsh","int","ip","reset"])
            console.print("  [green]TCP/IP reset.[/green]" if IS_ADMIN else "  [red]Needs Admin.[/red]")

        elif sel == 7:
            if IS_ADMIN: run_cmd(["netsh","winsock","reset"])
            console.print("  [green]Winsock reset.[/green]" if IS_ADMIN else "  [red]Needs Admin.[/red]")

        elif sel == 8:
            if not IS_ADMIN:
                console.print("  [red]Needs Admin.[/red]")
            else:
                out = run_ps("netsh wlan show profiles")
                profiles = [l.split(":")[1].strip() for l in out.splitlines() if "All User Profile" in l]
                t = Table(box=box.ROUNDED, header_style="bold cyan")
                t.add_column("Network",  width=30)
                t.add_column("Password", width=30)
                for p in profiles:
                    detail = run_ps(f'netsh wlan show profile name="{p}" key=clear')
                    pwd = next((l.split(":")[1].strip() for l in detail.splitlines()
                                if "Key Content" in l), "[dim]hidden[/dim]")
                    t.add_row(p, pwd)
                console.print(t)
        pause()


POWER_PLANS = {
    "Balanced":         "381b4222-f694-41f0-9685-ff5bb260df2e",
    "High Performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "Power Saver":      "a1841308-3541-4fab-bc81-f71556f20b4a",
    "Ultimate Performance": "e9a42b02-d5df-448d-aa00-03f14749eb61",
}

def power_plan_manager():
    while True:
        header("Power Plan Manager", "Pick a plan to activate")
        cur_out = run_ps("powercfg /getactivescheme")
        current = ""
        for name, guid in POWER_PLANS.items():
            if guid.lower() in cur_out.lower():
                current = name

        avail_out = run_ps("powercfg /list")

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",      width=4)
        t.add_column("Plan",   width=26)
        t.add_column("Status", width=14)
        t.add_column("GUID",   width=38, style="dim")
        plan_list = list(POWER_PLANS.items())
        for i, (name, guid) in enumerate(plan_list, 1):
            available = guid.lower() in avail_out.lower()
            if name == current:
                status = "[bold green]● ACTIVE[/bold green]"
            elif available:
                status = "[dim]available[/dim]"
            else:
                status = "[dim yellow]not installed[/dim yellow]"
            t.add_row(str(i), name, status, guid)
        console.print(t)
        console.print(f"\n  [dim]Current: [cyan]{current or 'Unknown'}[/cyan][/dim]")
        console.print("  [dim]Enter number to switch, U=Ultimate Performance (install), B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "u":
            if not IS_ADMIN:
                console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            console.print("  [yellow]Installing Ultimate Performance...[/yellow]")
            run_ps("powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61")
            console.print("  [green]Done. Select it from the list.[/green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(plan_list):
                name, guid = plan_list[idx]
                result = run_ps(f"powercfg /setactive {guid}")
                if "error" in result.lower():
                    console.print(f"  [red]Failed. Try installing it first (U).[/red]")
                else:
                    console.print(f"  [green]Switched to {name}.[/green]")
                time.sleep(0.8)


def toggle_reg(hive, path, name, enable_val, disable_val, enabled_check):
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_ALL_ACCESS)
        try:
            cur, _ = winreg.QueryValueEx(key, name)
            is_on  = (cur == enabled_check)
        except:
            is_on = False
        new_val = enable_val if not is_on else disable_val
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, new_val)
        winreg.CloseKey(key)
        return not is_on
    except Exception as e:
        return None

def get_reg_dword(hive, path, name):
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return val
    except:
        return None

def set_reg_dword(hive, path, name, val, create=True):
    try:
        if create:
            key = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_ALL_ACCESS)
        else:
            key = winreg.OpenKey(hive, path, 0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, val)
        winreg.CloseKey(key)
        return True
    except:
        return False

def game_optimizer():
    while True:
        game_mode = get_reg_dword(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\GameBar", "AllowAutoGameMode")
        gpu_sched = get_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode")
        hw_accel  = get_reg_dword(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Avalon.Graphics", "DisableHWAcceleration")
        mouse_accel = get_reg_dword(winreg.HKEY_CURRENT_USER,
            r"Control Panel\Mouse", "MouseSpeed")
        ntfs_ts   = run_ps("(Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem').NtfsDisableLastAccessUpdate")

        def st(val, on_val=1):
            return "[green]ON[/green]" if val == on_val else "[red]OFF[/red]"

        header("Game & Performance Optimizer")
        opts = [
            f"Game Mode                    {st(game_mode, 1)}",
            f"Hardware-Accelerated GPU Scheduling  {st(gpu_sched, 2)}",
            f"Hardware Acceleration (Avalon)  {st(hw_accel, 0)}",
            f"Mouse Acceleration  (OFF=better)  {'[green]OFF[/green]' if mouse_accel==0 else '[red]ON[/red]'}",
            f"NTFS Disable Last Access Update  {st(int(ntfs_ts) if ntfs_ts and ntfs_ts.isdigit() else 0, 1)}",
            "Apply ALL Gaming Tweaks  (one click)",
            "Boost Process Priority  (set current Python to High)",
        ]
        for i, opt in enumerate(opts, 1):
            console.print(f"  [bold cyan]{i}[/bold cyan]  {opt}")
        console.print(f"  [bold cyan]0[/bold cyan]  [dim]Back[/dim]\n")
        console.print("  [dim]Enter number to toggle[/dim]\n")

        raw = ask("").strip()
        if raw in ("0","b","q",""): return
        if not raw.isdigit(): continue
        n = int(raw)

        if n == 1:
            new = 0 if game_mode == 1 else 1
            set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AllowAutoGameMode", new)
            set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", new)
            console.print(f"  [green]Game Mode {'enabled' if new else 'disabled'}.[/green]"); time.sleep(0.6)

        elif n == 2:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            new = 1 if gpu_sched == 2 else 2
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", new)
            console.print(f"  [green]HAGS {'enabled' if new==2 else 'disabled'}. Restart to apply.[/green]"); time.sleep(1)

        elif n == 3:
            new = 0 if hw_accel == 1 else 1
            set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Avalon.Graphics",
                          "DisableHWAcceleration", new)
            console.print(f"  [green]HW Acceleration {'disabled' if new else 'enabled'}.[/green]"); time.sleep(0.6)

        elif n == 4:
            new = 0 if mouse_accel != 0 else 1
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", 0, winreg.KEY_ALL_ACCESS)
                winreg.SetValueEx(key, "MouseSpeed",       0, winreg.REG_SZ, str(new))
                winreg.SetValueEx(key, "MouseThreshold1",  0, winreg.REG_SZ, "0")
                winreg.SetValueEx(key, "MouseThreshold2",  0, winreg.REG_SZ, "0")
                winreg.CloseKey(key)
                console.print(f"  [green]Mouse acceleration {'enabled' if new else 'disabled'}.[/green]"); time.sleep(0.6)
            except Exception as e:
                console.print(f"  [red]{e}[/red]"); time.sleep(1)

        elif n == 5:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem", "NtfsDisableLastAccessUpdate", 1)
            console.print("  [green]NTFS last access update disabled.[/green]"); time.sleep(0.6)

        elif n == 6:
            console.print("  [yellow]Applying all gaming tweaks...[/yellow]")
            set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1)
            set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1)
            if IS_ADMIN:
                set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2)
                set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\FileSystem", "NtfsDisableLastAccessUpdate", 1)
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", 0, winreg.KEY_ALL_ACCESS)
                winreg.SetValueEx(key, "MouseSpeed",      0, winreg.REG_SZ, "0")
                winreg.SetValueEx(key, "MouseThreshold1", 0, winreg.REG_SZ, "0")
                winreg.SetValueEx(key, "MouseThreshold2", 0, winreg.REG_SZ, "0")
                winreg.CloseKey(key)
            except Exception:
                pass
            console.print("  [bold green]All gaming tweaks applied![/bold green]"); time.sleep(1)

        elif n == 7:
            try:
                p = psutil.Process(os.getpid())
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                console.print("  [green]This process set to High priority.[/green]"); time.sleep(0.7)
            except Exception as e:
                console.print(f"  [red]{e}[/red]"); time.sleep(1)


VFX_REG = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
PERF_REG = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
SYS_PERF = r"SYSTEM\CurrentControlSet\Control\PriorityControl"

VISUAL_TWEAKS = [
    ("Animations in taskbar",       winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarAnimations", 0, 1),
    ("Window animations",           winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics", "MinAnimate", 0, 1),
    ("Translucent selection box",   winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ListviewAlphaSelect", 0, 1),
    ("Drop shadows on desktop",     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ListviewShadow", 0, 1),
    ("Show window contents dragging",winreg.HKEY_CURRENT_USER,r"Control Panel\Desktop",               "DragFullWindows", 0, 1),
    ("Smooth-scroll list boxes",    winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop",               "SmoothScroll", 0, 1),
    ("Font smoothing (ClearType)",  winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop",               "FontSmoothing", 2, 0),
]

def visual_effects():
    while True:
        header("Visual Effects Optimizer", "Disable animations for faster feel")
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",       width=4)
        t.add_column("Effect",  width=34)
        t.add_column("Status",  width=12)
        for i, (label, hive, path, name, on_val, off_val) in enumerate(VISUAL_TWEAKS, 1):
            cur = get_reg_dword(hive, path, name)
            status = "[red]ON[/red]" if cur == on_val or cur == 1 else "[green]OFF[/green]"
            if name in ("FontSmoothing",):
                status = "[green]ON[/green]" if cur == on_val else "[dim]OFF[/dim]"
            t.add_row(str(i), label, status)
        console.print(t)
        console.print(f"\n  [dim]A=disable all animations  R=restore all  number=toggle  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            console.print("  [yellow]Disabling all animations...[/yellow]")
            for label, hive, path, name, on_val, off_val in VISUAL_TWEAKS:
                set_reg_dword(hive, path, name, off_val)
            set_reg_dword(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                "VisualFXSetting", 2)
            console.print("  [green]All animations disabled. Log out/in to see full effect.[/green]")
            time.sleep(1)
        elif raw == "r":
            console.print("  [yellow]Restoring defaults...[/yellow]")
            for label, hive, path, name, on_val, off_val in VISUAL_TWEAKS:
                set_reg_dword(hive, path, name, on_val)
            set_reg_dword(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
                "VisualFXSetting", 0)
            console.print("  [green]Restored.[/green]"); time.sleep(0.7)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(VISUAL_TWEAKS):
                label, hive, path, name, on_val, off_val = VISUAL_TWEAKS[idx]
                cur = get_reg_dword(hive, path, name)
                new = off_val if cur == on_val else on_val
                set_reg_dword(hive, path, name, new)
                console.print(f"  [green]Toggled.[/green]"); time.sleep(0.5)


BLOAT_SERVICES = [
    ("DiagTrack",           "Connected User Experiences & Telemetry"),
    ("dmwappushservice",    "WAP Push Message Routing"),
    ("SysMain",             "Superfetch / SysMain"),
    ("WSearch",             "Windows Search Indexing"),
    ("XblAuthManager",      "Xbox Live Auth Manager"),
    ("XblGameSave",         "Xbox Live Game Save"),
    ("XboxGipSvc",          "Xbox Accessory Management"),
    ("XboxNetApiSvc",       "Xbox Live Networking"),
    ("WerSvc",              "Windows Error Reporting"),
    ("RemoteRegistry",      "Remote Registry"),
    ("Fax",                 "Fax Service"),
    ("RetailDemo",          "Retail Demo Service"),
    ("MapsBroker",          "Downloaded Maps Manager"),
    ("lfsvc",               "Geolocation Service"),
    ("SharedAccess",        "Internet Connection Sharing"),
    ("PhoneSvc",            "Phone Service"),
    ("PrintNotify",         "Printer Extensions & Notifications"),
    ("Spooler",             "Print Spooler (disable if no printer)"),
]

def get_service_status(name):
    try:
        out = run_ps(f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status")
        return out.strip()
    except:
        return "Unknown"

def services_manager():
    if not IS_ADMIN:
        header("Services Manager")
        console.print("  [red]This tool requires Administrator.[/red]"); pause(); return
    while True:
        header("Background Services Manager", "Disable bloat services to free resources")
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",        width=4)
        t.add_column("Service",  width=16)
        t.add_column("Description",    width=38)
        t.add_column("Status",   width=10)
        with Progress(SpinnerColumn(), TextColumn("[dim]Loading...[/dim]"), console=console, transient=True) as p:
            task = p.add_task("", total=None)
            statuses = [(svc, desc, get_service_status(svc)) for svc, desc in BLOAT_SERVICES]
        for i, (svc, desc, status) in enumerate(statuses, 1):
            if status == "Running":
                col = "red"
            elif status in ("Stopped",""):
                col = "green"
            else:
                col = "dim"
            t.add_row(str(i), svc, desc, f"[{col}]{status or 'N/A'}[/{col}]")
        console.print(t)
        console.print("\n  [dim]number=toggle  A=stop all bloat  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            console.print("  [yellow]Stopping all bloat services...[/yellow]")
            for svc, _ in BLOAT_SERVICES:
                run_ps(f"Stop-Service -Name '{svc}' -Force -ErrorAction SilentlyContinue; "
                       f"Set-Service -Name '{svc}' -StartupType Disabled -ErrorAction SilentlyContinue")
            console.print("  [green]Done.[/green]"); time.sleep(0.8)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(statuses):
                svc, desc, status = statuses[idx]
                if status == "Running":
                    run_ps(f"Stop-Service -Name '{svc}' -Force -ErrorAction SilentlyContinue; "
                           f"Set-Service -Name '{svc}' -StartupType Disabled -ErrorAction SilentlyContinue")
                    console.print(f"  [green]{svc} stopped.[/green]")
                else:
                    run_ps(f"Set-Service -Name '{svc}' -StartupType Manual -ErrorAction SilentlyContinue; "
                           f"Start-Service -Name '{svc}' -ErrorAction SilentlyContinue")
                    console.print(f"  [green]{svc} started.[/green]")
                time.sleep(0.6)


def disk_optimizer():
    while True:
        header("Disk Optimizer")
        drives = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                drives.append((part.device, part.mountpoint, part.fstype, u))
            except Exception:
                pass

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",        width=4)
        t.add_column("Drive",    width=8)
        t.add_column("FS",       width=6)
        t.add_column("Used",     justify="right", width=10)
        t.add_column("Free",     justify="right", width=10)
        t.add_column("Usage",    width=30)
        for i, (dev, mp, fs, u) in enumerate(drives, 1):
            t.add_row(str(i), dev[:7], fs,
                      fmt_bytes(u.used), fmt_bytes(u.free),
                      pct_bar(u.percent, 22))
        console.print(t)
        console.print("\n  [dim]number=select drive  A=analyze all  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            for dev, mp, fs, _ in drives:
                letter = mp.rstrip("\\")
                console.print(f"  [yellow]Optimizing {letter}...[/yellow]")
                result = run_ps(f"Optimize-Volume -DriveLetter {letter[0]} -Verbose 2>&1")
                console.print(f"  [green]{letter} done.[/green]")
            time.sleep(0.8)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(drives):
                dev, mp, fs, _ = drives[idx]
                letter = mp.rstrip("\\")[0]
                opts2 = [
                    f"Analyze {letter}:\\",
                    f"Defragment {letter}:\\  (HDD)",
                    f"TRIM {letter}:\\  (SSD)",
                    f"Full optimize {letter}:\\  (Auto-detect)",
                ]
                sel2 = numbered_menu("Disk Optimizer", opts2, f"Drive {letter}:\\")
                if sel2 == -1: continue
                if not IS_ADMIN:
                    console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                header(f"Optimizing {letter}:\\...")
                if sel2 == 0:
                    out = run_ps(f"Optimize-Volume -DriveLetter {letter} -Analyze -Verbose 2>&1", timeout=60)
                elif sel2 == 1:
                    out = run_ps(f"Optimize-Volume -DriveLetter {letter} -Defrag -Verbose 2>&1", timeout=300)
                elif sel2 == 2:
                    out = run_ps(f"Optimize-Volume -DriveLetter {letter} -ReTrim -Verbose 2>&1", timeout=120)
                else:
                    out = run_ps(f"Optimize-Volume -DriveLetter {letter} -Verbose 2>&1", timeout=300)
                console.print(f"[dim]{out[:600]}[/dim]")
                console.print(f"\n  [green]Done.[/green]")
                pause()


def registry_cleaner():
    header("Registry Cleaner", "Scans for broken/orphaned entries")
    if not IS_ADMIN:
        console.print("  [red]Needs Administrator for full scan.[/red]\n")

    issues = []

    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
        task = prog.add_task("Scanning...", total=6)

        prog.update(task, description="Checking uninstall entries...")
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, sub in reg_paths:
            try:
                key = winreg.OpenKey(hive, sub)
                i = 0
                while True:
                    try:
                        subname = winreg.EnumKey(key, i)
                        subkey  = winreg.OpenKey(key, subname)
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            try:
                                install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                if install_loc and not Path(install_loc).exists():
                                    issues.append({
                                        "type": "Invalid Install Path",
                                        "desc": f"{name} → {install_loc}",
                                        "hive": hive, "sub": sub, "key": subname
                                    })
                            except Exception:
                                pass
                        except Exception:
                            pass
                        winreg.CloseKey(subkey)
                        i += 1
                    except OSError: break
                winreg.CloseKey(key)
            except Exception:
                pass
        prog.advance(task)

        prog.update(task, description="Checking file associations...")
        try:
            key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
            i = 0
            count = 0
            while count < 200:
                try:
                    ext = winreg.EnumKey(key, i)
                    if ext.startswith("."):
                        try:
                            ext_key  = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext)
                            prog_id, _ = winreg.QueryValueEx(ext_key, "")
                            winreg.CloseKey(ext_key)
                            if prog_id:
                                try:
                                    winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
                                except:
                                    issues.append({
                                        "type": "Broken File Association",
                                        "desc": f"{ext} → {prog_id} (missing)",
                                        "hive": None
                                    })
                        except Exception:
                            pass
                        count += 1
                    i += 1
                except OSError: break
            winreg.CloseKey(key)
        except Exception:
            pass
        prog.advance(task)

        prog.update(task, description="Checking shared DLLs...")
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs")
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    if not Path(name).exists():
                        issues.append({
                            "type": "Missing Shared DLL",
                            "desc": name,
                            "hive": winreg.HKEY_LOCAL_MACHINE,
                            "sub":  r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs",
                            "val":  name
                        })
                    i += 1
                except OSError: break
            winreg.CloseKey(key)
        except Exception:
            pass
        prog.advance(task)

        prog.update(task, description="Checking Run entries...")
        for hive, sub in [
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]:
            try:
                key = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        exe = val.strip('"').split('"')[0].split()[0] if val else ""
                        if exe and not Path(exe).exists():
                            issues.append({
                                "type": "Orphaned Run Entry",
                                "desc": f"{name} → {exe}",
                                "hive": hive, "sub": sub, "val_name": name
                            })
                        i += 1
                    except OSError: break
                winreg.CloseKey(key)
            except Exception:
                pass
        prog.advance(task)

        prog.update(task, description="Checking MUI cache...")
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
                                 0, winreg.KEY_READ)
            i = 0
            count = 0
            while count < 100:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    exe = name.split(".")[0] if "." in name else name
                    if exe and not Path(exe).exists() and "\\" in exe:
                        issues.append({
                            "type": "Stale MUI Cache",
                            "desc": exe[:60],
                            "hive": None
                        })
                        count += 1
                    i += 1
                except OSError: break
            winreg.CloseKey(key)
        except Exception:
            pass
        prog.advance(task)

        prog.update(task, description="Done.")
        prog.advance(task)

    header("Registry Cleaner", f"Found {len(issues)} issues")
    if not issues:
        console.print("  [green]Registry looks clean![/green]"); pause(); return

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("#",     width=5)
    t.add_column("Type",  width=26)
    t.add_column("Details", width=48)
    for i, issue in enumerate(issues[:40], 1):
        t.add_row(str(i), f"[yellow]{issue['type']}[/yellow]", f"[dim]{issue['desc'][:47]}[/dim]")
    console.print(t)
    if len(issues) > 40:
        console.print(f"  [dim]... and {len(issues)-40} more[/dim]")

    console.print(f"\n  [dim]C=clean all fixable issues  B=back[/dim]\n")
    raw = ask("").strip().lower()
    if raw == "c":
        fixed = 0
        for issue in issues:
            try:
                if issue["type"] == "Orphaned Run Entry" and issue.get("hive"):
                    k = winreg.OpenKey(issue["hive"], issue["sub"], 0, winreg.KEY_WRITE)
                    winreg.DeleteValue(k, issue["val_name"])
                    winreg.CloseKey(k)
                    fixed += 1
                elif issue["type"] == "Missing Shared DLL" and issue.get("hive"):
                    k = winreg.OpenKey(issue["hive"], issue["sub"], 0, winreg.KEY_WRITE)
                    winreg.DeleteValue(k, issue["val"])
                    winreg.CloseKey(k)
                    fixed += 1
            except Exception:
                pass
        console.print(f"  [green]Fixed {fixed} issues.[/green]")
    pause()


TELEMETRY_TWEAKS = [
    ("Disable Telemetry (AllowTelemetry=0)",
     winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0),
    ("Disable Advertising ID",
     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),
    ("Disable App Launch Tracking",
     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackProgs", 0),
    ("Disable Cortana Search",
     winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", 0),
    ("Disable Inking & Typing Telemetry",
     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1),
    ("Disable Feedback Frequency",
     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0),
    ("Disable Wi-Fi Sense",
     winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config", "AutoConnectAllowedOEM", 0),
    ("Disable Activity History",
     winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed", 0),
    ("Disable Location Tracking",
     winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Sensor\Overrides\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}", "SensorPermissionState", 0),
    ("Disable Tailored Experiences",
     winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0),
]

def telemetry_disabler():
    while True:
        header("Telemetry & Privacy", "Disable Windows spyware / data collection")
        if not IS_ADMIN:
            console.print("  [bold yellow]! Some tweaks require Admin to fully apply.[/bold yellow]\n")

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",       width=4)
        t.add_column("Tweak",   width=40)
        t.add_column("Status",  width=12)
        for i, (label, hive, path, name, target_val) in enumerate(TELEMETRY_TWEAKS, 1):
            cur = get_reg_dword(hive, path, name)
            if cur == target_val:
                status = "[green]DONE[/green]"
            elif cur is None:
                status = "[dim]not set[/dim]"
            else:
                status = "[red]ACTIVE[/red]"
            t.add_row(str(i), label, status)
        console.print(t)
        console.print("\n  [dim]A=apply all  number=toggle  S=stop telemetry services  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            console.print("  [yellow]Applying all privacy tweaks...[/yellow]")
            for label, hive, path, name, val in TELEMETRY_TWEAKS:
                set_reg_dword(hive, path, name, val)
            if IS_ADMIN:
                for svc in ("DiagTrack", "dmwappushservice"):
                    run_ps(f"Stop-Service -Name {svc} -Force -ErrorAction SilentlyContinue; "
                           f"Set-Service -Name {svc} -StartupType Disabled -ErrorAction SilentlyContinue")
            console.print("  [bold green]All privacy tweaks applied![/bold green]"); time.sleep(1)
        elif raw == "s":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            for svc in ("DiagTrack","dmwappushservice","PcaSvc","WerSvc","diagnosticshub.standardcollector.service"):
                run_ps(f"Stop-Service -Name {svc} -Force -ErrorAction SilentlyContinue; "
                       f"Set-Service -Name {svc} -StartupType Disabled -ErrorAction SilentlyContinue")
            console.print("  [green]Telemetry services stopped.[/green]"); time.sleep(0.8)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(TELEMETRY_TWEAKS):
                label, hive, path, name, val = TELEMETRY_TWEAKS[idx]
                cur = get_reg_dword(hive, path, name)
                new = 1 if cur == val else val
                set_reg_dword(hive, path, name, new)
                console.print(f"  [green]Toggled.[/green]"); time.sleep(0.5)


def memory_optimizer():
    while True:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        header("Memory Optimizer")

        console.print(Panel(
            f"  RAM   {pct_bar(mem.percent)}\n"
            f"        Used [cyan]{fmt_bytes(mem.used)}[/cyan]  "
            f"Free [green]{fmt_bytes(mem.available)}[/green]  "
            f"Total {fmt_bytes(mem.total)}\n\n"
            f"  Swap  {pct_bar(swap.percent)}\n"
            f"        Used [cyan]{fmt_bytes(swap.used)}[/cyan]  "
            f"Free [green]{fmt_bytes(swap.free)}[/green]  "
            f"Total {fmt_bytes(swap.total)}",
            title="[cyan]Memory Status[/cyan]", style="cyan"
        ))

        opts = [
            "Clear Working Sets  (free cached RAM)",
            "Top memory processes",
            "Virtual Memory settings info",
            "Disable Superfetch / SysMain  (Admin)",
        ]
        console.print()
        for i, opt in enumerate(opts, 1):
            console.print(f"  [bold cyan]{i}[/bold cyan]  {opt}")
        console.print(f"  [bold cyan]0[/bold cyan]  [dim]Back[/dim]\n")

        raw = ask("").strip()
        if raw in ("0","b","q",""): return
        if not raw.isdigit(): continue
        n = int(raw)

        if n == 1:
            console.print("  [yellow]Clearing memory...[/yellow]")
            gc.collect()
            try:
                ctypes.windll.psapi.EmptyWorkingSet(
                    ctypes.windll.kernel32.GetCurrentProcess())
            except Exception:
                pass
            mem2   = psutil.virtual_memory()
            gained = max(0, mem2.available - mem.available)
            console.print(f"  [green]Done. ~{fmt_bytes(gained)} freed.[/green]")
            time.sleep(0.8)

        elif n == 2:
            t = Table(box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Process",  width=32)
            t.add_column("RAM",      justify="right", width=12)
            t.add_column("CPU%",     justify="right", width=8)
            for p in sorted(psutil.process_iter(["name","memory_info","cpu_percent"]),
                            key=lambda x: x.info["memory_info"].rss if x.info.get("memory_info") else 0,
                            reverse=True)[:15]:
                try:
                    t.add_row(p.info["name"][:31],
                              fmt_bytes(p.info["memory_info"].rss),
                              f"{p.info['cpu_percent'] or 0:.1f}")
                except Exception:
                    pass
            console.print(t)
            pause()

        elif n == 3:
            out = run_ps("Get-WmiObject -Class Win32_PageFileUsage | "
                         "Select-Object Name,AllocatedBaseSize,CurrentUsage | Format-List")
            console.print(f"[dim]{out}[/dim]")
            pause()

        elif n == 4:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            run_ps("Stop-Service -Name SysMain -Force -ErrorAction SilentlyContinue; "
                   "Set-Service -Name SysMain -StartupType Disabled -ErrorAction SilentlyContinue")
            console.print("  [green]SysMain/Superfetch disabled.[/green]"); time.sleep(0.8)


def system_info():
    header("System Information")
    with Progress(SpinnerColumn(), TextColumn("[cyan]Gathering info...[/cyan]"),
                  console=console, transient=True) as p:
        t = p.add_task("", total=None)

        cpu       = platform.processor()
        cpu_cores = psutil.cpu_count(logical=False)
        cpu_logic = psutil.cpu_count(logical=True)
        cpu_freq  = psutil.cpu_freq()
        mem       = psutil.virtual_memory()
        disks     = psutil.disk_partitions(all=False)
        boot      = datetime.fromtimestamp(psutil.boot_time())
        uptime    = datetime.now() - boot
        gpu_info  = run_ps("(Get-WmiObject Win32_VideoController).Name")
        os_info   = run_ps("(Get-WmiObject Win32_OperatingSystem).Caption")
        bios      = run_ps("(Get-WmiObject Win32_BIOS).SMBIOSBIOSVersion")
        mb        = run_ps("(Get-WmiObject Win32_BaseBoard).Product")
        total_disk= sum(psutil.disk_usage(p.mountpoint).total
                        for p in disks if p.mountpoint)

    t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
    t.add_column("Key",   style="bold cyan", width=22)
    t.add_column("Value", style="white",     width=46)
    t.add_row("OS",             os_info)
    t.add_row("CPU",            f"{cpu[:44]}")
    t.add_row("Cores",          f"{cpu_cores} physical  /  {cpu_logic} logical")
    t.add_row("CPU Freq",       f"{cpu_freq.current:.0f} MHz  (max {cpu_freq.max:.0f} MHz)" if cpu_freq else "?")
    t.add_row("RAM",            f"{fmt_bytes(mem.total)}  ({fmt_bytes(mem.available)} free)")
    t.add_row("Total Disk",     fmt_bytes(total_disk))
    t.add_row("GPU",            gpu_info[:44] if gpu_info else "?")
    t.add_row("Motherboard",    mb[:44] if mb else "?")
    t.add_row("BIOS",           bios[:44] if bios else "?")
    t.add_row("Boot Time",      boot.strftime("%Y-%m-%d %H:%M:%S"))
    t.add_row("Uptime",         str(uptime).split(".")[0])
    t.add_row("Python",         sys.version.split()[0])
    t.add_row("Admin",          "[green]Yes[/green]" if IS_ADMIN else "[yellow]No[/yellow]")
    console.print(t)

    console.print("\n[bold]Drives:[/bold]")
    dt = Table(box=box.SIMPLE, header_style="bold cyan")
    dt.add_column("Drive",  width=8)
    dt.add_column("FS",     width=6)
    dt.add_column("Total",  justify="right", width=10)
    dt.add_column("Used",   justify="right", width=10)
    dt.add_column("Free",   justify="right", width=10)
    dt.add_column("",       width=30)
    for part in disks:
        try:
            u = psutil.disk_usage(part.mountpoint)
            dt.add_row(part.device[:7], part.fstype,
                       fmt_bytes(u.total), fmt_bytes(u.used), fmt_bytes(u.free),
                       pct_bar(u.percent, 22))
        except Exception:
            pass
    console.print(dt)
    pause()


def live_monitor():
    header("Live Performance Monitor", "Press ENTER to stop")
    console.print("  [dim]Monitoring — press ENTER to stop[/dim]\n")
    import threading
    stop = False
    def wait(): 
        nonlocal stop
        input()
        stop = True
    threading.Thread(target=wait, daemon=True).start()

    io_prev  = psutil.disk_io_counters()
    net_prev = psutil.net_io_counters()
    t_prev   = time.time()

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while not stop:
            t_now   = time.time()
            elapsed = max(t_now - t_prev, 0.01)
            t_prev  = t_now

            cpu_all  = psutil.cpu_percent(percpu=True)
            cpu_avg  = sum(cpu_all)/len(cpu_all)
            mem      = psutil.virtual_memory()
            io_now   = psutil.disk_io_counters()
            net_now  = psutil.net_io_counters()

            disk_r   = (io_now.read_bytes  - io_prev.read_bytes)  / elapsed
            disk_w   = (io_now.write_bytes - io_prev.write_bytes) / elapsed
            net_up   = (net_now.bytes_sent - net_prev.bytes_sent) / elapsed
            net_dn   = (net_now.bytes_recv - net_prev.bytes_recv) / elapsed

            io_prev  = io_now
            net_prev = net_now

            cpu_bar = pct_bar(cpu_avg)
            mem_bar = pct_bar(mem.percent)

            core_str = "  ".join(
                f"[{'red' if p>80 else 'yellow' if p>50 else 'green'}]{p:4.0f}%[/]"
                for p in cpu_all
            )

            out = (
                f"  [bold cyan]CPU[/bold cyan]   {cpu_bar}\n"
                f"         {core_str}\n\n"
                f"  [bold cyan]RAM[/bold cyan]   {mem_bar}\n"
                f"         Used [cyan]{fmt_bytes(mem.used)}[/cyan]  "
                f"Free [green]{fmt_bytes(mem.available)}[/green]\n\n"
                f"  [bold cyan]DISK[/bold cyan]  "
                f"R [green]{fmt_bytes(disk_r):>9}/s[/green]  "
                f"W [yellow]{fmt_bytes(disk_w):>9}/s[/yellow]\n\n"
                f"  [bold cyan]NET[/bold cyan]   "
                f"Up [cyan]{fmt_bytes(net_up):>9}/s[/cyan]  "
                f"Dn [green]{fmt_bytes(net_dn):>9}/s[/green]\n"
            )
            live.update(Panel(out, title="[cyan]Live Monitor[/cyan]", style="cyan"))
            time.sleep(0.5)
            if stop: break



CPU_TWEAKS = [
    ("Disable CPU Core Parking",
     winreg.HKEY_LOCAL_MACHINE,
     r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings\54533251-82be-4824-96c1-47b60b740d00\0cc5b647-c1df-4637-891a-dec35c318583",
     "ValueMax", 0,
     "Forces all CPU cores to stay active. Best for gaming/performance."),

    ("High Performance CPU Throttle Policy",
     winreg.HKEY_LOCAL_MACHINE,
     r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings\54533251-82be-4824-96c1-47b60b740d00\893dee8e-2bef-41e0-89c6-b55d0929964c",
     "ValueMax", 100,
     "Set CPU max state to 100% — prevents throttling."),

    ("Disable Idle Power Savings",
     winreg.HKEY_LOCAL_MACHINE,
     r"SYSTEM\CurrentControlSet\Control\Power\PowerSettings\54533251-82be-4824-96c1-47b60b740d00\68f262a7-f621-4069-b9a5-4874169be23c",
     "ValueMax", 0,
     "Stops CPU from entering low-power idle states."),

    ("Disable Spectre/Meltdown Mitigations (CAUTION)",
     winreg.HKEY_LOCAL_MACHINE,
     r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
     "FeatureSettingsOverride", 3,
     "Can improve CPU performance 5-15%. Security trade-off."),

    ("Increase System Responsiveness (Multimedia)",
     winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
     "SystemResponsiveness", 0,
     "Sets multimedia system responsiveness to maximum (0=best for games)."),

    ("GPU Priority for Games",
     winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
     "GPU Priority", 8,
     "Raises GPU scheduling priority for game processes."),

    ("CPU Priority for Games",
     winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
     "Priority", 6,
     "Raises CPU scheduling priority for game processes."),

    ("Disable HPET (High Precision Event Timer)",
     None, None, None, None,
     "Use cmd: bcdedit /deletevalue useplatformclock — can reduce latency."),
]

def cpu_tweaks():
    while True:
        header("CPU Priority Tweaks", "Fine-tune CPU scheduling & performance")
        if not IS_ADMIN:
            console.print("  [bold yellow]! Most tweaks require Admin.[/bold yellow]\n")

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",      width=4)
        t.add_column("Tweak",  width=36)
        t.add_column("Status", width=10)
        t.add_column("Info",   width=30, style="dim")
        for i, (label, hive, path, name, val, info) in enumerate(CPU_TWEAKS, 1):
            if hive and path and name:
                cur = get_reg_dword(hive, path, name)
                status = "[green]SET[/green]" if cur == val else "[dim]default[/dim]"
            else:
                status = "[dim]cmd[/dim]"
            t.add_row(str(i), label, status, info[:29])
        console.print(t)
        console.print("\n  [dim]A=apply all safe tweaks   number=toggle   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            console.print("  [yellow]Applying CPU tweaks...[/yellow]")
            for label, hive, path, name, val, info in CPU_TWEAKS:
                if hive and path and name and "CAUTION" not in label:
                    set_reg_dword(hive, path, name, val)
            run_ps("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")
            console.print("  [bold green]CPU tweaks applied![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(CPU_TWEAKS):
                label, hive, path, name, val, info = CPU_TWEAKS[idx]
                if hive is None:
                    console.print(f"  [yellow]Run manually:[/yellow] bcdedit /deletevalue useplatformclock")
                    pause(); continue
                if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                if "CAUTION" in label:
                    if not confirm("This has security implications. Continue?"): continue
                cur = get_reg_dword(hive, path, name)
                new = 1 if cur == val else val
                set_reg_dword(hive, path, name, new)
                console.print(f"  [green]Done.[/green]"); time.sleep(0.5)


def gpu_optimizer():
    while True:
        header("GPU Optimization", "Registry & driver-level GPU tweaks")

        gpu_info = run_ps("(Get-WmiObject Win32_VideoController | Select-Object -First 1).Name")
        driver   = run_ps("(Get-WmiObject Win32_VideoController | Select-Object -First 1).DriverVersion")
        vram     = run_ps("(Get-WmiObject Win32_VideoController | Select-Object -First 1).AdapterRAM")
        try:
            vram_gb = f"{int(vram) / (1024**3):.1f} GB" if vram and vram.isdigit() else "?"
        except:
            vram_gb = "?"

        console.print(Panel(
            f"  GPU:    [cyan]{gpu_info}[/cyan]\n"
            f"  Driver: [dim]{driver}[/dim]\n"
            f"  VRAM:   [cyan]{vram_gb}[/cyan]",
            title="[cyan]Detected GPU[/cyan]", style="cyan"
        ))
        console.print()

        GPU_TWEAKS = [
            ("Hardware-Accelerated GPU Scheduling (HAGS)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2,
             "Reduces GPU latency. Requires Windows 10 2004+ & modern GPU."),
            ("Disable GPU Preemption (lower latency)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
             "TdrLevel", 0,
             "Stops Windows from preempting the GPU. Better frame times."),
            ("Increase GPU TDR Delay",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
             "TdrDelay", 10,
             "Stops 'display driver stopped' crashes under load."),
            ("Force GPU Performance Mode",
             winreg.HKEY_CURRENT_USER,
             r"Software\Microsoft\DirectX\UserGpuPreferences",
             "DirectXUserGlobalSettings", None,
             "Sets global GPU preference to High Performance."),
        ]

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",      width=4)
        t.add_column("Tweak",  width=40)
        t.add_column("Status", width=10)
        t.add_column("Info",   width=28, style="dim")
        for i, (label, hive, path, name, val, info) in enumerate(GPU_TWEAKS, 1):
            if val is not None:
                cur    = get_reg_dword(hive, path, name)
                status = "[green]SET[/green]" if cur == val else "[dim]default[/dim]"
            else:
                status = "[dim]special[/dim]"
            t.add_row(str(i), label, status, info[:27])
        console.print(t)
        console.print("\n  [dim]A=apply all   O=open GPU control panel   number=toggle   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "o":
            for exe in [r"C:\Program Files\NVIDIA Corporation\Control Panel Client\nvcplui.exe",
                        r"C:\Program Files\AMD\CNext\CNext\RadeonSoftware.exe"]:
                if Path(exe).exists():
                    subprocess.Popen([exe]); break
            else:
                subprocess.Popen(["control","desk.cpl,,3"])
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            for label, hive, path, name, val, info in GPU_TWEAKS:
                if val is not None:
                    set_reg_dword(hive, path, name, val)
                else:
                    try:
                        k = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_ALL_ACCESS)
                        winreg.SetValueEx(k, name, 0, winreg.REG_SZ,
                                          "VRROptimizeEnable=0;GpuPreference=2;")
                        winreg.CloseKey(k)
                    except Exception:
                        pass
            console.print("  [bold green]GPU tweaks applied! Restart recommended.[/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(GPU_TWEAKS):
                label, hive, path, name, val, info = GPU_TWEAKS[idx]
                if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                if val is not None:
                    cur = get_reg_dword(hive, path, name)
                    new = 0 if cur == val else val
                    set_reg_dword(hive, path, name, new)
                    console.print(f"  [green]Toggled.[/green]"); time.sleep(0.5)


def storage_tweaks():
    while True:
        header("SSD / HDD Tweaks", "Storage-specific performance settings")

        drives_info = run_ps(
            "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,Size | ConvertTo-Csv -NoTypeInformation"
        )
        console.print("[bold]Detected Storage:[/bold]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        t.add_column("Drive",     width=38)
        t.add_column("Type",      width=8)
        t.add_column("Size",      justify="right", width=10)
        for line in drives_info.splitlines()[1:]:
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 3:
                name  = parts[0][:37]
                mtype = parts[1]
                try:
                    sz = fmt_bytes(int(parts[2]))
                except:
                    sz = parts[2]
                col = "cyan" if "SSD" in mtype or "NVMe" in mtype else "yellow"
                t.add_row(name, f"[{col}]{mtype}[/{col}]", sz)
        console.print(t)
        console.print()

        STORAGE_TWEAKS_LIST = [
            ("Disable Last Access Timestamp (NTFS)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\FileSystem",
             "NtfsDisableLastAccessUpdate", 1,
             "Reduces unnecessary disk writes. Good for both SSD & HDD."),
            ("Enable Write Caching (better perf)",
             None, None, None, None,
             "Via Device Manager > Disk > Policies. Speeds up writes."),
            ("Disable 8.3 Filename Generation",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\FileSystem",
             "NtfsDisable8dot3NameCreation", 1,
             "Reduces filesystem overhead on NTFS volumes."),
            ("Disable Paging Executive",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
             "DisablePagingExecutive", 1,
             "Keeps kernel in RAM — reduces disk paging. Good if RAM > 8GB."),
            ("Large System Cache",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
             "LargeSystemCache", 1,
             "Increases file system cache size. Helps HDD sequential reads."),
            ("Disable Hibernation (free disk space)",
             None, None, None, None,
             "Frees hiberfil.sys (same size as RAM). Run: powercfg -h off"),
            ("Disable Prefetch (SSD only — HDD keep ON)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters",
             "EnablePrefetcher", 0,
             "SSDs don't benefit from prefetch. Reduces writes."),
            ("Disable Superfetch/SysMain (SSD only)",
             None, None, None, None,
             "Via Services Manager. Unnecessary on SSD, wastes RAM."),
        ]

        t2 = Table(box=box.ROUNDED, header_style="bold cyan")
        t2.add_column("#",      width=4)
        t2.add_column("Tweak",  width=38)
        t2.add_column("Status", width=10)
        t2.add_column("Notes",  width=28, style="dim")
        for i, (label, hive, path, name, val, info) in enumerate(STORAGE_TWEAKS_LIST, 1):
            if hive and path and name:
                cur    = get_reg_dword(hive, path, name)
                status = "[green]SET[/green]" if cur == val else "[dim]default[/dim]"
            else:
                status = "[dim]manual[/dim]"
            t2.add_row(str(i), label, status, info[:27])
        console.print(t2)
        console.print("\n  [dim]A=apply all registry tweaks   number=toggle   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            console.print("  [yellow]Applying storage tweaks...[/yellow]")
            for label, hive, path, name, val, _ in STORAGE_TWEAKS_LIST:
                if hive and path and name:
                    set_reg_dword(hive, path, name, val)
            console.print("  [bold green]Storage tweaks applied![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(STORAGE_TWEAKS_LIST):
                label, hive, path, name, val, info = STORAGE_TWEAKS_LIST[idx]
                if hive is None:
                    if "Hibernation" in label:
                        if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                        run_cmd(["powercfg", "-h", "off"])
                        console.print("  [green]Hibernation disabled. hiberfil.sys removed.[/green]")
                    else:
                        console.print(f"  [yellow]Manual step:[/yellow] {info}")
                    pause(); continue
                if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                cur = get_reg_dword(hive, path, name)
                new = 0 if cur == val else val
                set_reg_dword(hive, path, name, new)
                console.print(f"  [green]Toggled.[/green]"); time.sleep(0.5)


def network_latency_tweaks():
    while True:
        header("Network Latency Tweaks", "Gaming-focused network optimizations")

        NET_TWEAKS = [
            ("Disable Nagle's Algorithm  (lower TCP latency)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces",
             "TcpAckFrequency", 1,
             "Sends packets immediately instead of batching. Reduces ping."),
            ("TCP No Delay",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces",
             "TCPNoDelay", 1,
             "Forces TCP to send data without delay."),
            ("Disable Network Throttling Index",
             winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
             "NetworkThrottlingIndex", 0xFFFFFFFF,
             "Removes Windows network throttle on non-multimedia apps."),
            ("Increase IRPStackSize  (larger network buffers)",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters",
             "IRPStackSize", 32,
             "Larger I/O request packet stack. Helps with LAN performance."),
            ("Set TTL to 64",
             winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
             "DefaultTTL", 64,
             "Standard TTL. Some ISPs prioritize packets with TTL=64."),
            ("Disable AutoTuning  (fixes high latency on some setups)",
             None, None, None, None,
             "Run: netsh int tcp set global autotuninglevel=disabled"),
            ("Enable RSS (Receive Side Scaling)",
             None, None, None, None,
             "Run: netsh int tcp set global rss=enabled"),
            ("Flush DNS on apply",
             None, None, None, None,
             "Clears DNS cache after applying tweaks."),
        ]

        try:
            t0  = time.time()
            s   = socket.create_connection(("8.8.8.8", 53), timeout=2)
            ms  = (time.time() - t0) * 1000
            s.close()
            ping_str = f"[green]{ms:.1f}ms[/green]" if ms < 30 else f"[yellow]{ms:.1f}ms[/yellow]" if ms < 80 else f"[red]{ms:.1f}ms[/red]"
        except:
            ping_str = "[red]timeout[/red]"
        console.print(f"  Current latency to 8.8.8.8: {ping_str}\n")

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",      width=4)
        t.add_column("Tweak",  width=40)
        t.add_column("Status", width=10)
        t.add_column("Info",   width=28, style="dim")
        for i, (label, hive, path, name, val, info) in enumerate(NET_TWEAKS, 1):
            if hive and path and name:
                if "Interfaces" in path:
                    status = "[dim]per-iface[/dim]"
                else:
                    cur    = get_reg_dword(hive, path, name)
                    status = "[green]SET[/green]" if cur == val else "[dim]default[/dim]"
            else:
                status = "[dim]cmd[/dim]"
            t.add_row(str(i), label, status, info[:27])
        console.print(t)
        console.print("\n  [dim]A=apply all   P=ping test   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "p":
            header("Ping Test")
            for host in ["8.8.8.8", "1.1.1.1", "google.com", "steamgames.com"]:
                try:
                    times = []
                    for _ in range(3):
                        t0 = time.time()
                        s  = socket.create_connection((host, 80 if "." in host else 53), timeout=2)
                        times.append((time.time()-t0)*1000)
                        s.close()
                    avg = sum(times)/len(times)
                    col = "green" if avg<20 else "yellow" if avg<60 else "red"
                    console.print(f"  {host:<20} [{col}]{avg:6.1f}ms[/{col}]")
                except:
                    console.print(f"  {host:<20} [red]timeout[/red]")
            pause()
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            console.print("  [yellow]Applying network latency tweaks...[/yellow]")
            for label, hive, path, name, val, _ in NET_TWEAKS:
                if hive and path and name and "Interfaces" not in path:
                    set_reg_dword(hive, path, name, val)
            try:
                ifaces_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces",
                    0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        iface = winreg.EnumKey(ifaces_key, i)
                        iface_path = rf"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{iface}"
                        set_reg_dword(winreg.HKEY_LOCAL_MACHINE, iface_path, "TcpAckFrequency", 1)
                        set_reg_dword(winreg.HKEY_LOCAL_MACHINE, iface_path, "TCPNoDelay", 1)
                        i += 1
                    except OSError: break
                winreg.CloseKey(ifaces_key)
            except Exception:
                pass
            run_cmd(["netsh","int","tcp","set","global","autotuninglevel=disabled"])
            run_cmd(["netsh","int","tcp","set","global","rss=enabled"])
            run_cmd(["ipconfig","/flushdns"])
            console.print("  [bold green]Network tweaks applied![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(NET_TWEAKS):
                label, hive, path, name, val, info = NET_TWEAKS[idx]
                if hive is None:
                    console.print(f"  [yellow]Manual:[/yellow] {info}"); pause(); continue
                if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                if "Interfaces" in path:
                    try:
                        ik = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces", 0, winreg.KEY_READ)
                        j = 0
                        while True:
                            try:
                                iface = winreg.EnumKey(ik, j)
                                ip = rf"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{iface}"
                                cur = get_reg_dword(winreg.HKEY_LOCAL_MACHINE, ip, name)
                                set_reg_dword(winreg.HKEY_LOCAL_MACHINE, ip, name, 0 if cur == val else val)
                                j += 1
                            except OSError: break
                        winreg.CloseKey(ik)
                    except Exception:
                        pass
                else:
                    cur = get_reg_dword(hive, path, name)
                    set_reg_dword(hive, path, name, 0 if cur == val else val)
                console.print(f"  [green]Toggled.[/green]"); time.sleep(0.5)


def sleep_settings():
    while True:
        header("Hibernation & Sleep Settings", "Power state configuration")

        sleep_out = run_ps(
            "powercfg /query SCHEME_CURRENT SUB_SLEEP | "
            "Select-String 'Current AC Power Setting Index' | "
            "ForEach-Object { $_.Line.Trim() }"
        )
        hib_out = run_ps("powercfg /a")

        console.print("[bold]Available Power States:[/bold]")
        for line in hib_out.splitlines():
            line = line.strip()
            if not line: continue
            if "following sleep states" in line.lower() or "available" in line.lower():
                console.print(f"  [cyan]{line}[/cyan]")
            elif line.startswith("S"):
                console.print(f"    [green]{line}[/green]")
            elif "not available" in line.lower():
                console.print(f"    [dim]{line}[/dim]")
        console.print()

        opts = [
            "Disable Hibernation  (free ~RAM size of disk space)",
            "Enable Hibernation",
            "Set Sleep timeout — AC power",
            "Set Sleep timeout — Battery",
            "Set Hibernate timeout — AC power",
            "Disable Fast Startup  (can cause issues)",
            "Enable Fast Startup",
            "Set monitor timeout — AC",
            "Set monitor timeout — Battery",
            "Disable Wake Timers  (stops random wakeups)",
            "Show current power scheme settings",
        ]
        for i, opt in enumerate(opts, 1):
            console.print(f"  [bold cyan]{i:>2}[/bold cyan]  {opt}")
        console.print(f"  [bold cyan] 0[/bold cyan]  [dim]Back[/dim]\n")

        raw = ask("").strip()
        if raw in ("0","b","q",""): return
        if not raw.isdigit(): continue
        n = int(raw)

        if not IS_ADMIN and n in (1,2,3,4,5,6,7,8,9,10):
            console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue

        if n == 1:
            run_cmd(["powercfg", "-h", "off"])
            console.print("  [green]Hibernation disabled. hiberfil.sys removed.[/green]")
        elif n == 2:
            run_cmd(["powercfg", "-h", "on"])
            console.print("  [green]Hibernation enabled.[/green]")
        elif n == 3:
            mins = ask("Sleep timeout in minutes (0=never)", "30")
            secs = int(mins) * 60 if mins.isdigit() else 0
            run_cmd(["powercfg","/change","standby-timeout-ac", str(int(mins) if mins.isdigit() else 0)])
            console.print(f"  [green]AC sleep set to {mins} min.[/green]")
        elif n == 4:
            mins = ask("Battery sleep timeout in minutes (0=never)", "15")
            run_cmd(["powercfg","/change","standby-timeout-dc", str(int(mins) if mins.isdigit() else 0)])
            console.print(f"  [green]Battery sleep set to {mins} min.[/green]")
        elif n == 5:
            mins = ask("Hibernate timeout in minutes (0=never)", "60")
            run_cmd(["powercfg","/change","hibernate-timeout-ac", str(int(mins) if mins.isdigit() else 0)])
            console.print(f"  [green]Hibernate AC set to {mins} min.[/green]")
        elif n == 6:
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
                "HiberbootEnabled", 0)
            console.print("  [green]Fast Startup disabled.[/green]")
        elif n == 7:
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
                "HiberbootEnabled", 1)
            console.print("  [green]Fast Startup enabled.[/green]")
        elif n == 8:
            mins = ask("Monitor off timeout AC in minutes (0=never)", "15")
            run_cmd(["powercfg","/change","monitor-timeout-ac", str(int(mins) if mins.isdigit() else 0)])
            console.print(f"  [green]Monitor AC timeout set to {mins} min.[/green]")
        elif n == 9:
            mins = ask("Monitor off timeout Battery in minutes (0=never)", "5")
            run_cmd(["powercfg","/change","monitor-timeout-dc", str(int(mins) if mins.isdigit() else 0)])
            console.print(f"  [green]Monitor battery timeout set to {mins} min.[/green]")
        elif n == 10:
            run_ps("powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 0; "
                   "powercfg /setactive SCHEME_CURRENT")
            console.print("  [green]Wake timers disabled.[/green]")
        elif n == 11:
            out = run_ps("powercfg /query SCHEME_CURRENT")
            console.print(f"[dim]{out[:1200]}[/dim]")
            pause(); continue

        time.sleep(0.7)


def full_optimize():
    header("Full System Optimization", "One-click apply all safe tweaks")
    console.print(Panel(
        "  This will apply ALL safe performance tweaks:\n\n"
        "  [cyan]*[/cyan] Switch to High Performance power plan\n"
        "  [cyan]*[/cyan] Game Mode + HAGS on\n"
        "  [cyan]*[/cyan] Mouse acceleration off\n"
        "  [cyan]*[/cyan] Disable all animations\n"
        "  [cyan]*[/cyan] CPU scheduling tweaks\n"
        "  [cyan]*[/cyan] NTFS last access update off\n"
        "  [cyan]*[/cyan] Disable 8.3 filenames\n"
        "  [cyan]*[/cyan] Network Throttling Index removed\n"
        "  [cyan]*[/cyan] Disable Nagle's on all interfaces\n"
        "  [cyan]*[/cyan] Telemetry off\n"
        "  [cyan]*[/cyan] Stop bloat services (Xbox, WER, DiagTrack)\n"
        "  [cyan]*[/cyan] Clear junk files\n"
        "  [cyan]*[/cyan] Flush DNS",
        title="[bold yellow]Full Optimize[/bold yellow]",
        style="yellow"
    ))
    if not IS_ADMIN:
        console.print("  [bold red]! Run as Administrator for full effect.[/bold red]\n")

    if not confirm("Apply all optimizations now?"):
        return

    steps = []

    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
        task = prog.add_task("", total=13)

        prog.update(task, description="Power plan: High Performance...")
        run_ps("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")
        steps.append("[green]Power plan set to High Performance[/green]")
        prog.advance(task)

        prog.update(task, description="Game Mode & HAGS...")
        set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1)
        set_reg_dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1)
        if IS_ADMIN:
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2)
        steps.append("[green]Game Mode + HAGS enabled[/green]")
        prog.advance(task)

        prog.update(task, description="Mouse acceleration off...")
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(k, "MouseSpeed",      0, winreg.REG_SZ, "0")
            winreg.SetValueEx(k, "MouseThreshold1", 0, winreg.REG_SZ, "0")
            winreg.SetValueEx(k, "MouseThreshold2", 0, winreg.REG_SZ, "0")
            winreg.CloseKey(k)
            steps.append("[green]Mouse acceleration disabled[/green]")
        except:
            steps.append("[dim]Mouse accel skipped[/dim]")
        prog.advance(task)

        prog.update(task, description="Disabling animations...")
        for label, hive, path, name, on_val, off_val in VISUAL_TWEAKS:
            set_reg_dword(hive, path, name, off_val)
        set_reg_dword(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
            "VisualFXSetting", 2)
        steps.append("[green]Animations disabled[/green]")
        prog.advance(task)

        prog.update(task, description="CPU scheduling tweaks...")
        set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
            "SystemResponsiveness", 0)
        set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
            "GPU Priority", 8)
        set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
            "Priority", 6)
        steps.append("[green]CPU/GPU scheduling priorities set[/green]")
        prog.advance(task)

        prog.update(task, description="NTFS tweaks...")
        if IS_ADMIN:
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem", "NtfsDisableLastAccessUpdate", 1)
            set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem", "NtfsDisable8dot3NameCreation", 1)
        steps.append("[green]NTFS last-access + 8.3 names disabled[/green]")
        prog.advance(task)

        prog.update(task, description="Network throttling...")
        set_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
            "NetworkThrottlingIndex", 0xFFFFFFFF)
        steps.append("[green]Network throttle removed[/green]")
        prog.advance(task)

        prog.update(task, description="Nagle's Algorithm on all interfaces...")
        try:
            ik = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces",
                0, winreg.KEY_READ)
            j = 0
            while True:
                try:
                    iface = winreg.EnumKey(ik, j)
                    ip = rf"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{iface}"
                    set_reg_dword(winreg.HKEY_LOCAL_MACHINE, ip, "TcpAckFrequency", 1)
                    set_reg_dword(winreg.HKEY_LOCAL_MACHINE, ip, "TCPNoDelay", 1)
                    j += 1
                except OSError: break
            winreg.CloseKey(ik)
            steps.append("[green]Nagle's Algorithm disabled[/green]")
        except:
            steps.append("[dim]Nagle's skipped[/dim]")
        prog.advance(task)

        prog.update(task, description="Telemetry off...")
        for label, hive, path, name, val in TELEMETRY_TWEAKS:
            set_reg_dword(hive, path, name, val)
        steps.append("[green]Telemetry disabled[/green]")
        prog.advance(task)

        prog.update(task, description="Stopping bloat services...")
        if IS_ADMIN:
            for svc in ("DiagTrack","dmwappushservice","XblAuthManager","XblGameSave",
                        "XboxNetApiSvc","WerSvc","SysMain"):
                run_ps(f"Stop-Service -Name {svc} -Force -ErrorAction SilentlyContinue; "
                       f"Set-Service -Name {svc} -StartupType Disabled -ErrorAction SilentlyContinue")
        steps.append("[green]Bloat services stopped[/green]")
        prog.advance(task)

        prog.update(task, description="Clearing junk files...")
        for path in [Path(os.environ.get("TEMP","")),
                     Path("C:/Windows/Temp"),
                     LAD / "CrashDumps",
                     LAD / "Microsoft/Windows/WER/ReportArchive",
                     LAD / "D3DSCache"]:
            if path and path.exists():
                try:
                    for item in path.iterdir():
                        try:
                            if item.is_file(): item.unlink(missing_ok=True)
                            elif item.is_dir(): shutil.rmtree(item, ignore_errors=True)
                        except Exception:
                            pass
                except Exception:
                    pass
        steps.append("[green]Junk files cleared[/green]")
        prog.advance(task)

        prog.update(task, description="Flushing DNS...")
        run_cmd(["ipconfig","/flushdns"])
        run_cmd(["netsh","int","tcp","set","global","autotuninglevel=disabled"])
        run_cmd(["netsh","int","tcp","set","global","rss=enabled"])
        steps.append("[green]DNS flushed + TCP tuned[/green]")
        prog.advance(task)

        prog.update(task, description="Memory cleanup...")
        gc.collect()
        steps.append("[green]Memory cleared[/green]")
        prog.advance(task)

    console.print("\n  [bold green]Full optimization complete![/bold green]\n")
    for s in steps:
        console.print(f"  [dim]•[/dim] {s}")
    console.print("\n  [dim]Some changes (HAGS, services) require a restart.[/dim]")
    pause()



def system_repair():
    opts = [
        "SFC /scannow  (scan & repair system files)",
        "DISM CheckHealth",
        "DISM ScanHealth",
        "DISM RestoreHealth  (repair Windows image)",
        "CHKDSK on C:\\  (schedule for next boot)",
        "Reset Windows Update components",
        "Clear Windows Update cache",
        "Repair Windows Store apps",
        "Reset network stack  (netsh)",
        "Run all repair steps  (full repair)",
    ]
    while True:
        sel = numbered_menu("System Repair", opts, "Admin required for most")
        if sel == -1: return
        header("System Repair", opts[sel])
        if not IS_ADMIN:
            console.print("  [red]Needs Administrator.[/red]"); pause(); continue

        if sel == 0:
            console.print("  [yellow]Running SFC... this can take several minutes.[/yellow]\n")
            result = subprocess.run(["sfc", "/scannow"], capture_output=False, text=True)
            console.print("\n  [green]SFC complete.[/green]")

        elif sel == 1:
            console.print("  [yellow]Running DISM CheckHealth...[/yellow]\n")
            subprocess.run(["dism", "/online", "/cleanup-image", "/checkhealth"])
            console.print("\n  [green]Done.[/green]")

        elif sel == 2:
            console.print("  [yellow]Running DISM ScanHealth... (may take a while)[/yellow]\n")
            subprocess.run(["dism", "/online", "/cleanup-image", "/scanhealth"])
            console.print("\n  [green]Done.[/green]")

        elif sel == 3:
            console.print("  [yellow]Running DISM RestoreHealth... (needs internet, may take 10-20 min)[/yellow]\n")
            subprocess.run(["dism", "/online", "/cleanup-image", "/restorehealth"])
            console.print("\n  [green]Done.[/green]")

        elif sel == 4:
            console.print("  [yellow]Scheduling CHKDSK on C:\\ for next boot...[/yellow]")
            result = subprocess.run(["chkdsk", "C:", "/f", "/r"], input="Y\n",
                                    capture_output=True, text=True)
            console.print("  [green]CHKDSK scheduled. Restart to run.[/green]")

        elif sel == 5:
            console.print("  [yellow]Resetting Windows Update components...[/yellow]")
            cmds = [
                ["net", "stop", "wuauserv"],
                ["net", "stop", "cryptsvc"],
                ["net", "stop", "bits"],
                ["net", "stop", "msiserver"],
            ]
            for c in cmds: run_cmd(c)
            shutil.rmtree("C:/Windows/SoftwareDistribution", ignore_errors=True)
            shutil.rmtree("C:/Windows/System32/catroot2", ignore_errors=True)
            cmds2 = [
                ["net", "start", "wuauserv"],
                ["net", "start", "cryptsvc"],
                ["net", "start", "bits"],
                ["net", "start", "msiserver"],
            ]
            for c in cmds2: run_cmd(c)
            console.print("  [green]Windows Update components reset.[/green]")

        elif sel == 6:
            p = Path("C:/Windows/SoftwareDistribution/Download")
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
            console.print("  [green]Windows Update cache cleared.[/green]")

        elif sel == 7:
            console.print("  [yellow]Repairing Windows Store apps...[/yellow]")
            run_ps("Get-AppXPackage -AllUsers | ForEach-Object { "
                   "Add-AppxPackage -DisableDevelopmentMode -Register \"$($_.InstallLocation)\\AppXManifest.xml\" "
                   "-ErrorAction SilentlyContinue }")
            console.print("  [green]Store apps re-registered.[/green]")

        elif sel == 8:
            console.print("  [yellow]Resetting network stack...[/yellow]")
            run_cmd(["netsh", "int", "ip", "reset"])
            run_cmd(["netsh", "winsock", "reset"])
            run_cmd(["netsh", "advfirewall", "reset"])
            run_cmd(["ipconfig", "/flushdns"])
            run_cmd(["ipconfig", "/release"])
            run_cmd(["ipconfig", "/renew"])
            console.print("  [green]Network stack reset. Restart recommended.[/green]")

        elif sel == 9:
            console.print("  [yellow]Running full repair sequence...[/yellow]\n")
            steps = [
                (["sfc", "/scannow"],                                     "SFC scan"),
                (["dism","/online","/cleanup-image","/checkhealth"],      "DISM CheckHealth"),
                (["dism","/online","/cleanup-image","/restorehealth"],    "DISM RestoreHealth"),
            ]
            with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                          console=console) as prog:
                task = prog.add_task("", total=len(steps))
                for cmd, desc in steps:
                    prog.update(task, description=desc)
                    subprocess.run(cmd, capture_output=True)
                    prog.advance(task)
            console.print("  [bold green]Full repair complete.[/bold green]")

        pause()


def event_log_viewer():
    log_sources = ["System", "Application", "Security", "Setup"]
    while True:
        sel = numbered_menu("Event Log Viewer", log_sources + ["Custom log name"], "Pick a log")
        if sel == -1: return

        if sel == len(log_sources):
            log = ask("Log name")
        else:
            log = log_sources[sel]

        level_sel = numbered_menu("Event Log Viewer", [
            "All levels",
            "Errors only",
            "Errors + Warnings",
            "Critical only",
        ], f"Filter level for {log}")
        if level_sel == -1: continue

        level_filter = {
            0: "",
            1: " | Where-Object { $_.LevelDisplayName -eq 'Error' }",
            2: " | Where-Object { $_.LevelDisplayName -in @('Error','Warning') }",
            3: " | Where-Object { $_.LevelDisplayName -eq 'Critical' }",
        }[level_sel]

        header(f"Event Log — {log}", "Loading last 50 events...")
        console.print("  [yellow]Fetching events...[/yellow]\n")

        out = run_ps(
            f"Get-WinEvent -LogName '{log}' -MaxEvents 50 -ErrorAction SilentlyContinue"
            f"{level_filter} | "
            f"Select-Object TimeCreated,LevelDisplayName,Id,Message | "
            f"ConvertTo-Csv -NoTypeInformation",
            timeout=20
        )

        if not out or "No events" in out:
            console.print("  [dim]No events found.[/dim]"); pause(); continue

        t = Table(box=box.ROUNDED, header_style="bold cyan", expand=True)
        t.add_column("Time",    width=20)
        t.add_column("Level",   width=10)
        t.add_column("ID",      width=6, justify="right")
        t.add_column("Message", width=55)

        for line in out.splitlines()[1:51]:
            try:
                parts = line.strip().strip('"').split('","')
                if len(parts) < 4: continue
                ts      = parts[0][:19]
                level   = parts[1]
                eid     = parts[2]
                msg     = parts[3][:54].replace("\n"," ")
                if level == "Error":    lc = "red"
                elif level == "Warning": lc = "yellow"
                elif level == "Critical": lc = "bold red"
                else:                    lc = "dim"
                t.add_row(ts, f"[{lc}]{level}[/{lc}]", eid, msg)
            except Exception:
                pass
        console.print(t)
        pause()


def env_editor():
    while True:
        header("Environment Variables Editor", "W/S=move  E=edit  N=new  D=delete  T=toggle user/system  B=back")

        scope_opts = ["User variables", "System variables"]
        scope_sel  = numbered_menu("Environment Variables", scope_opts, "Scope?")
        if scope_sel == -1: return
        scope = "User" if scope_sel == 0 else "Machine"
        reg_hive = winreg.HKEY_CURRENT_USER if scope == "User" else winreg.HKEY_LOCAL_MACHINE
        reg_path = r"Environment" if scope == "User" else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

        cur = 0
        while True:
            env_vars = []
            try:
                key = winreg.OpenKey(reg_hive, reg_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, val, vtype = winreg.EnumValue(key, i)
                        env_vars.append((name, str(val)[:80], vtype))
                        i += 1
                    except OSError: break
                winreg.CloseKey(key)
            except Exception as e:
                console.print(f"  [red]{e}[/red]"); pause(); break

            env_vars.sort(key=lambda x: x[0].lower())

            header(f"Environment Variables — {scope}", "W/S=move  E=edit  N=new  D=delete  B=back")
            t = Table(box=box.SIMPLE, header_style="bold cyan", expand=True)
            t.add_column("",      width=3)
            t.add_column("Name",  width=28)
            t.add_column("Value", width=52)
            start = max(0, cur - 15)
            for i, (name, val, _) in enumerate(env_vars[start:start+30], start):
                arrow = "[yellow]>[/yellow]" if i == cur else " "
                style = "cyan" if i == cur else "white"
                v     = val if len(val) <= 52 else val[:49] + "..."
                t.add_row(arrow, f"[{style}]{name}[/{style}]", f"[dim]{v}[/dim]")
            console.print(t)
            console.print(f"\n  [dim]{len(env_vars)} variables   W/S=move  E=edit  N=new  D=delete  B=back[/dim]")

            raw = ask("").strip().lower()
            if raw == "b": break
            elif raw == "w": cur = max(0, cur - 1)
            elif raw == "s": cur = min(len(env_vars)-1, cur + 1)
            elif raw == "n":
                new_name = ask("Variable name")
                new_val  = ask("Value")
                if new_name:
                    try:
                        key = winreg.OpenKey(reg_hive, reg_path, 0, winreg.KEY_ALL_ACCESS)
                        winreg.SetValueEx(key, new_name, 0, winreg.REG_EXPAND_SZ, new_val)
                        winreg.CloseKey(key)
                        console.print(f"  [green]Created {new_name}.[/green]"); time.sleep(0.6)
                    except Exception as e:
                        console.print(f"  [red]{e}[/red]"); time.sleep(1)
            elif raw == "e" and env_vars:
                name, val, vtype = env_vars[cur]
                new_val = ask(f"New value for {name}", val)
                try:
                    key = winreg.OpenKey(reg_hive, reg_path, 0, winreg.KEY_ALL_ACCESS)
                    winreg.SetValueEx(key, name, 0, vtype, new_val)
                    winreg.CloseKey(key)
                    console.print(f"  [green]Updated.[/green]"); time.sleep(0.6)
                except Exception as e:
                    console.print(f"  [red]{e}[/red]"); time.sleep(1)
            elif raw == "d" and env_vars:
                name = env_vars[cur][0]
                if confirm(f"Delete variable '{name}'?"):
                    try:
                        key = winreg.OpenKey(reg_hive, reg_path, 0, winreg.KEY_ALL_ACCESS)
                        winreg.DeleteValue(key, name)
                        winreg.CloseKey(key)
                        cur = max(0, cur - 1)
                        console.print(f"  [green]Deleted.[/green]"); time.sleep(0.6)
                    except Exception as e:
                        console.print(f"  [red]{e}[/red]"); time.sleep(1)


def firewall_viewer():
    opts = [
        "Show open/listening ports",
        "Show active connections",
        "Show firewall rules  (inbound)",
        "Show firewall rules  (outbound)",
        "Enable/Disable firewall",
        "Add firewall rule",
        "Delete firewall rule",
        "Firewall status overview",
    ]
    while True:
        sel = numbered_menu("Firewall & Open Ports", opts)
        if sel == -1: return
        header("Firewall & Open Ports", opts[sel])

        if sel == 0:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Port",     justify="right", width=7)
            t.add_column("Proto",    width=6)
            t.add_column("State",    width=12)
            t.add_column("Process",  width=20)
            t.add_column("PID",      justify="right", width=7)
            for c in sorted(psutil.net_connections("inet"), key=lambda x: x.laddr.port if x.laddr else 0):
                if c.status in ("LISTEN", "LISTENING") or not c.raddr:
                    try:
                        pname = psutil.Process(c.pid).name() if c.pid else "?"
                    except: pname = "?"
                    proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
                    port  = str(c.laddr.port) if c.laddr else "?"
                    t.add_row(port, proto, f"[green]{c.status}[/green]",
                              pname[:19], str(c.pid or "?"))
            console.print(t)

        elif sel == 1:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Local",    width=22)
            t.add_column("Remote",   width=22)
            t.add_column("State",    width=14)
            t.add_column("Process",  width=18)
            shown = 0
            for c in psutil.net_connections("inet"):
                if c.raddr and c.status == "ESTABLISHED":
                    try: pname = psutil.Process(c.pid).name() if c.pid else "?"
                    except: pname = "?"
                    la = f"{c.laddr.ip}:{c.laddr.port}"
                    ra = f"{c.raddr.ip}:{c.raddr.port}"
                    t.add_row(la, ra, "[cyan]ESTABLISHED[/cyan]", pname[:17])
                    shown += 1
                    if shown >= 25: break
            console.print(t)

        elif sel == 2:
            console.print("  [yellow]Loading inbound rules...[/yellow]")
            out = run_ps(
                "Get-NetFirewallRule -Direction Inbound -Enabled True | "
                "Select-Object DisplayName,Action,Profile,Description | "
                "Select-Object -First 40 | ConvertTo-Csv -NoTypeInformation",
                timeout=20
            )
            t = Table(box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Rule",    width=38)
            t.add_column("Action",  width=8)
            t.add_column("Profile", width=12)
            for line in out.splitlines()[1:]:
                try:
                    p = line.strip().strip('"').split('","')
                    if len(p) >= 3:
                        col = "green" if p[1]=="Allow" else "red"
                        t.add_row(p[0][:37], f"[{col}]{p[1]}[/{col}]", p[2][:11])
                except Exception:
                    pass
            console.print(t)

        elif sel == 3:
            console.print("  [yellow]Loading outbound rules...[/yellow]")
            out = run_ps(
                "Get-NetFirewallRule -Direction Outbound -Enabled True | "
                "Select-Object DisplayName,Action,Profile | "
                "Select-Object -First 40 | ConvertTo-Csv -NoTypeInformation",
                timeout=20
            )
            t = Table(box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Rule",    width=38)
            t.add_column("Action",  width=8)
            t.add_column("Profile", width=12)
            for line in out.splitlines()[1:]:
                try:
                    p = line.strip().strip('"').split('","')
                    if len(p) >= 3:
                        col = "green" if p[1]=="Allow" else "red"
                        t.add_row(p[0][:37], f"[{col}]{p[1]}[/{col}]", p[2][:11])
                except Exception:
                    pass
            console.print(t)

        elif sel == 4:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); pause(); continue
            profile_sel = numbered_menu("Firewall", ["Enable all profiles", "Disable all profiles  (CAUTION)"])
            if profile_sel == 0:
                run_cmd(["netsh","advfirewall","set","allprofiles","state","on"])
                console.print("  [green]Firewall enabled.[/green]")
            elif profile_sel == 1:
                if confirm("Really disable firewall?"):
                    run_cmd(["netsh","advfirewall","set","allprofiles","state","off"])
                    console.print("  [yellow]Firewall disabled.[/yellow]")

        elif sel == 5:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); pause(); continue
            name     = ask("Rule name")
            port     = ask("Port number")
            proto    = ask("Protocol (TCP/UDP)", "TCP")
            direction= ask("Direction (in/out)", "in")
            action   = ask("Action (allow/block)", "allow")
            cmd = ["netsh","advfirewall","firewall","add","rule",
                   f"name={name}", f"protocol={proto.upper()}",
                   f"localport={port}", f"dir={direction}", f"action={action}"]
            if run_cmd(cmd):
                console.print(f"  [green]Rule '{name}' added.[/green]")
            else:
                console.print(f"  [red]Failed.[/red]")

        elif sel == 6:
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); pause(); continue
            name = ask("Rule name to delete")
            run_cmd(["netsh","advfirewall","firewall","delete","rule",f"name={name}"])
            console.print(f"  [green]Rule deleted (if it existed).[/green]")

        elif sel == 7:
            out = run_ps("Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction | Format-Table -AutoSize")
            console.print(f"[cyan]{out}[/cyan]")

        pause()


def hash_and_password():
    opts = [
        "Hash a file  (MD5 / SHA1 / SHA256 / SHA512)",
        "Hash a string",
        "Compare two file hashes",
        "Generate secure password",
        "Generate multiple passwords",
        "Check password strength",
    ]
    while True:
        sel = numbered_menu("Hash Checker & Password Generator", opts)
        if sel == -1: return
        header("Hash & Password", opts[sel])

        if sel == 0:
            path = ask("File path (drag & drop works)")
            path = path.strip().strip('"')
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            console.print(f"  [yellow]Hashing {Path(path).name}...[/yellow]\n")
            size = Path(path).stat().st_size
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Algorithm", width=10)
            t.add_column("Hash",      width=70)
            for algo in ["md5","sha1","sha256","sha512"]:
                h = hashlib.new(algo)
                with open(path,"rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                t.add_row(algo.upper(), h.hexdigest())
            console.print(t)
            console.print(f"\n  [dim]File size: {fmt_bytes(size)}[/dim]")

        elif sel == 1:
            text = ask("String to hash")
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Algorithm", width=10)
            t.add_column("Hash",      width=70)
            for algo in ["md5","sha1","sha256","sha512"]:
                h = hashlib.new(algo, text.encode()).hexdigest()
                t.add_row(algo.upper(), h)
            console.print(t)

        elif sel == 2:
            p1 = ask("First file path").strip().strip('"')
            p2 = ask("Second file path").strip().strip('"')
            for p in [p1, p2]:
                if not Path(p).exists():
                    console.print(f"  [red]Not found: {p}[/red]"); pause(); continue
            def sha256(p):
                h = hashlib.sha256()
                with open(p,"rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
                return h.hexdigest()
            h1, h2 = sha256(p1), sha256(p2)
            console.print(f"  File 1: [cyan]{h1}[/cyan]")
            console.print(f"  File 2: [cyan]{h2}[/cyan]")
            if h1 == h2:
                console.print("\n  [bold green]✓ Files are IDENTICAL[/bold green]")
            else:
                console.print("\n  [bold red]✗ Files are DIFFERENT[/bold red]")

        elif sel == 3:
            length  = ask("Length", "20")
            symbols = confirm("Include symbols?")
            chars   = string.ascii_letters + string.digits
            if symbols: chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
            try:
                length = int(length)
            except:
                length = 20
            pwd = "".join(secrets.choice(chars) for _ in range(length))
            console.print(f"\n  [bold green]{pwd}[/bold green]\n")
            score = 0
            if length >= 12: score += 1
            if length >= 16: score += 1
            if any(c.isupper() for c in pwd): score += 1
            if any(c.isdigit() for c in pwd): score += 1
            if any(c in "!@#$%^&*()" for c in pwd): score += 1
            strength = ["Very Weak","Weak","Fair","Strong","Very Strong","Excellent"][min(score,5)]
            col = ["red","red","yellow","cyan","green","bold green"][min(score,5)]
            console.print(f"  Strength: [{col}]{strength}[/{col}]")

        elif sel == 4:
            count  = int(ask("How many?", "10"))
            length = int(ask("Length", "16"))
            chars  = string.ascii_letters + string.digits + "!@#$%^&*"
            console.print()
            t = Table(box=box.SIMPLE, show_header=False)
            t.add_column("#",   width=4, style="dim")
            t.add_column("Password", width=40, style="green")
            for i in range(min(count, 50)):
                t.add_row(str(i+1), "".join(secrets.choice(chars) for _ in range(length)))
            console.print(t)

        elif sel == 5:
            pwd = ask("Password to check")
            score = 0
            issues = []
            if len(pwd) >= 8:  score += 1
            else: issues.append("Too short (< 8 chars)")
            if len(pwd) >= 12: score += 1
            if len(pwd) >= 16: score += 1
            if any(c.isupper() for c in pwd): score += 1
            else: issues.append("No uppercase letters")
            if any(c.islower() for c in pwd): score += 1
            else: issues.append("No lowercase letters")
            if any(c.isdigit() for c in pwd): score += 1
            else: issues.append("No numbers")
            if any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pwd): score += 1
            else: issues.append("No special characters")
            score = min(score, 5)
            strength = ["Very Weak","Weak","Fair","Strong","Very Strong","Excellent"][score]
            col      = ["red","red","yellow","cyan","green","bold green"][score]
            console.print(f"\n  Strength: [{col}]{strength}[/{col}]  (score {score}/5)")
            console.print(f"  Length:   {len(pwd)} chars\n")
            if issues:
                for issue in issues:
                    console.print(f"  [yellow]- {issue}[/yellow]")
            else:
                console.print("  [green]Looks solid![/green]")

        pause()


def http_get(url, timeout=8):
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return None
    except (socket.timeout, OSError) as e:
        return None

def http_json(url, timeout=8):
    data = http_get(url, timeout)
    if data:
        try: return json.loads(data)
        except (json.JSONDecodeError, ValueError): return None
    return None


def ip_domain_lookup():
    while True:
        header("IP / Domain Lookup", "Geolocation, WHOIS, ASN info")
        target = ask("Enter IP or domain (or B to go back)").strip()
        if target.lower() in ("b",""):
            return

        console.print(f"\n  [yellow]Looking up {target}...[/yellow]\n")

        ip = target
        hostname = ""
        try:
            resolved = socket.gethostbyname(target)
            if resolved != target:
                hostname = target
                ip       = resolved
                console.print(f"  Resolved: [cyan]{target}[/cyan] → [green]{ip}[/green]\n")
        except Exception:
            pass

        data = http_json(f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query,reverse,mobile,proxy,hosting")

        if data and data.get("status") == "success":
            t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
            t.add_column("Field",  style="bold cyan", width=18)
            t.add_column("Value",  style="white",     width=46)
            fields = [
                ("IP",          data.get("query","")),
                ("Hostname",    data.get("reverse","") or hostname),
                ("Country",     data.get("country","")),
                ("Region",      data.get("regionName","")),
                ("City",        data.get("city","")),
                ("ZIP",         data.get("zip","")),
                ("Lat/Lon",     f"{data.get('lat','')} , {data.get('lon','')}"),
                ("Timezone",    data.get("timezone","")),
                ("ISP",         data.get("isp","")),
                ("Org",         data.get("org","")),
                ("ASN",         data.get("as","")),
                ("Mobile",      "[yellow]Yes[/yellow]" if data.get("mobile") else "No"),
                ("Proxy/VPN",   "[red]Yes[/red]" if data.get("proxy") else "No"),
                ("Hosting/DC",  "[yellow]Yes[/yellow]" if data.get("hosting") else "No"),
            ]
            for k, v in fields:
                if v: t.add_row(k, str(v))
            console.print(t)
        else:
            console.print(f"  [red]Lookup failed for {ip}[/red]")

        console.print("\n  [bold]DNS Records:[/bold]")
        for rtype in ["A", "MX", "NS", "TXT"]:
            try:
                out = subprocess.run(
                    ["nslookup", f"-type={rtype}", target],
                    capture_output=True, text=True, timeout=5
                ).stdout
                lines = [l.strip() for l in out.splitlines()
                         if l.strip() and "Server:" not in l and "Address:" not in l
                         and "***" not in l and target in l or rtype in l]
                if lines:
                    console.print(f"  [cyan]{rtype}:[/cyan]")
                    for l in lines[:4]:
                        console.print(f"    [dim]{l}[/dim]")
            except Exception:
                pass

        pause()


def dns_lookup():
    while True:
        header("DNS Record Lookup")
        target = ask("Domain to query (B=back)").strip()
        if target.lower() in ("b",""): return

        console.print(f"\n  [yellow]Querying DNS for {target}...[/yellow]\n")

        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "PTR", "SRV"]
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Type",    width=7)
        t.add_column("Records", width=66)

        for rtype in record_types:
            try:
                result = subprocess.run(
                    ["nslookup", f"-type={rtype}", target, "8.8.8.8"],
                    capture_output=True, text=True, timeout=5
                )
                lines = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if not line: continue
                    if any(skip in line for skip in ["Server:","Address:","Non-authoritative"]): continue
                    if target in line or rtype.lower() in line.lower() or "=" in line:
                        clean = line.replace(target,"").strip(" \t=,")
                        if clean and len(clean) > 2:
                            lines.append(clean[:65])
                if lines:
                    t.add_row(f"[cyan]{rtype}[/cyan]", "\n".join(lines[:5]))
            except Exception:
                pass

        console.print(t)

        console.print("\n  [bold]WHOIS (basic):[/bold]")
        whois_data = http_json(f"https://api.whoisjsonapi.com/whoisserver/WhoisService?domainName={target}&outputFormat=JSON")
        if whois_data:
            try:
                wr = whois_data.get("WhoisRecord", {})
                for field in ["registrarName","createdDate","expiresDate","updatedDate","status"]:
                    val = wr.get(field,"")
                    if val: console.print(f"  [cyan]{field}:[/cyan] {str(val)[:60]}")
            except Exception:
                pass
        else:
            try:
                out = subprocess.run(["whois", target], capture_output=True, text=True, timeout=8).stdout
                for line in out.splitlines()[:15]:
                    if ":" in line and line.strip():
                        console.print(f"  [dim]{line.strip()[:70]}[/dim]")
            except:
                console.print("  [dim]WHOIS not available (install whois or check internet)[/dim]")

        pause()


def reverse_ip_lookup():
    while True:
        header("Reverse IP Lookup", "Find domains hosted on an IP")
        ip = ask("IP address (B=back)").strip()
        if ip.lower() in ("b",""): return

        console.print(f"\n  [yellow]Reverse lookup for {ip}...[/yellow]\n")

        try:
            result = subprocess.run(["nslookup", ip], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if "name =" in line.lower() or "arpa" in line.lower():
                    console.print(f"  PTR: [cyan]{line.strip()}[/cyan]")
        except Exception:
            pass

        try:
            host = socket.gethostbyaddr(ip)
            console.print(f"  Hostname: [cyan]{host[0]}[/cyan]")
            if host[1]:
                for alias in host[1]:
                    console.print(f"  Alias:    [dim]{alias}[/dim]")
        except Exception:
            pass

        data = http_json(f"http://ip-api.com/json/{ip}")
        if data and data.get("status") == "success":
            console.print(f"\n  [bold]Location:[/bold]")
            t = Table(box=box.SIMPLE, show_header=False)
            t.add_column("k", style="cyan", width=12)
            t.add_column("v", style="white", width=40)
            t.add_row("Country",  data.get("country",""))
            t.add_row("City",     f"{data.get('city','')} {data.get('regionName','')}")
            t.add_row("ISP",      data.get("isp",""))
            t.add_row("Org",      data.get("org",""))
            t.add_row("ASN",      data.get("as",""))
            t.add_row("Proxy",    "[red]Yes[/red]" if data.get("proxy") else "No")
            console.print(t)

        console.print(f"\n  [bold]Domains on this IP (ViewDNS):[/bold]")
        page = http_get(f"https://viewdns.info/reverseip/?host={ip}&t=1")
        if page:
            import re
            domains = re.findall(r'<td>([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})</td>', page)
            domains = [d for d in domains if len(d) > 4 and "viewdns" not in d][:20]
            if domains:
                for d in domains:
                    console.print(f"    [dim]{d}[/dim]")
            else:
                console.print("  [dim]None found or blocked.[/dim]")
        else:
            console.print("  [dim]Could not reach ViewDNS.[/dim]")

        pause()


USERNAME_SITES = [
    ("GitHub",      "https://github.com/{}"),
    ("Twitter/X",   "https://twitter.com/{}"),
    ("Instagram",   "https://www.instagram.com/{}/"),
    ("Reddit",      "https://www.reddit.com/user/{}"),
    ("TikTok",      "https://www.tiktok.com/@{}"),
    ("YouTube",     "https://www.youtube.com/@{}"),
    ("Twitch",      "https://www.twitch.tv/{}"),
    ("Steam",       "https://steamcommunity.com/id/{}"),
    ("LinkedIn",    "https://www.linkedin.com/in/{}"),
    ("Pinterest",   "https://www.pinterest.com/{}/"),
    ("Snapchat",    "https://www.snapchat.com/add/{}"),
    ("Spotify",     "https://open.spotify.com/user/{}"),
    ("SoundCloud",  "https://soundcloud.com/{}"),
    ("Patreon",     "https://www.patreon.com/{}"),
    ("DeviantArt",  "https://www.deviantart.com/{}"),
    ("Roblox",      "https://www.roblox.com/user.aspx?username={}"),
    ("Replit",      "https://replit.com/@{}"),
    ("Codecademy",  "https://www.codecademy.com/profiles/{}"),
    ("HackerNews",  "https://news.ycombinator.com/user?id={}"),
    ("Keybase",     "https://keybase.io/{}"),
    ("Medium",      "https://medium.com/@{}"),
    ("Substack",    "https://{}.substack.com"),
    ("Gitlab",      "https://gitlab.com/{}"),
    ("Bitbucket",   "https://bitbucket.org/{}"),
    ("Discord",     "https://discord.gg/{}"),
    ("Mastodon",    "https://mastodon.social/@{}"),
    ("Bluesky",     "https://bsky.app/profile/{}"),
    ("Telegram",    "https://t.me/{}"),
    ("Quora",       "https://www.quora.com/profile/{}"),
    ("Tumblr",      "https://{}.tumblr.com"),
    ("VimeoUser",   "https://vimeo.com/{}"),
    ("Disqus",      "https://disqus.com/by/{}/"),
    ("Gravatar",    "https://gravatar.com/{}"),
    ("Flickr",      "https://www.flickr.com/photos/{}@N"),
    ("IMDb",        "https://www.imdb.com/user/{}"),
    ("Archive.org", "https://web.archive.org/web/20230101000000*/{}"),
]

def username_search():
    while True:
        header("Username Search", "Deep search across 37+ platforms & Discord")
        username = ask("Username to search (B=back)").strip()
        if username.lower() in ("b",""): return

        console.print(f"\n  [yellow]Searching for '[bold]{username}[/bold]' across {len(USERNAME_SITES)} platforms...[/yellow]\n")
        found    = []
        notfound = []

        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), TextColumn("{task.completed}/{task.total}"),
                      console=console) as prog:
            task = prog.add_task("Checking...", total=len(USERNAME_SITES))
            for site, url_tmpl in USERNAME_SITES:
                url = url_tmpl.format(username)
                prog.update(task, description=f"[dim]{site}[/dim]")
                try:
                    ctx = ssl.create_default_context()
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                        code = r.status
                        if code == 200:
                            found.append((site, url, "Web"))
                        else:
                            notfound.append(site)
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        notfound.append(site)
                    else:
                        found.append((site, url, "Web"))  # might exist, just restricted
                except:
                    notfound.append(site)
                prog.advance(task)

        console.print(f"\n  [cyan]Scanning Discord databases...[/cyan]")
        discord_results = []
        discord_sources = [
            (f"Discord User Search (discordapp.com)", f"https://discordapp.com/api/v9/users/{username}"),
            (f"Discord API User Lookup", f"https://api.discord.id/users?query={username}"),
            (f"Discord Bot Finder", f"https://discord.bots.gg/bots?search={username}"),
            (f"Discord.me Servers", f"https://discord.me/search?q={username}"),
        ]
        
        try:
            for name, url in discord_sources:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=3, context=ssl.create_default_context()) as r:
                        if r.status == 200:
                            discord_results.append((name, url))
                except Exception:
                    pass
        except Exception:
            pass

        console.print(f"  [cyan]Scanning public search engines...[/cyan]")
        search_results = []
        search_queries = [
            ("Google (exact name)", f"https://www.google.com/search?q=\"{username}\""),
            ("Bing (exact name)", f"https://www.bing.com/search?q=\"{username}\""),
            ("DuckDuckGo", f"https://duckduckgo.com/?q=\"{username}\""),
        ]
        search_results = [(name, url) for name, url in search_queries]

        header(f"Username Search — '[bold cyan]{username}[/bold cyan]'")
        
        if found:
            console.print(f"  [bold green]Found on {len(found)} platforms:[/bold green]\n")
            for site, url, source in found:
                console.print(f"  [green]✓[/green] [bold cyan]{site:<20}[/bold cyan] [dim]{url}[/dim]")

        if discord_results:
            console.print(f"\n  [bold magenta]Discord Deep Search Results ({len(discord_results)}):[/bold magenta]\n")
            for name, url in discord_results:
                console.print(f"  [magenta]◆[/magenta] [bold]{name:<25}[/bold cyan] [dim]{url}[/dim]")

        if search_results:
            console.print(f"\n  [bold yellow]Public Search Engines (use these to find profiles):[/bold yellow]\n")
            for name, url in search_results:
                console.print(f"  [yellow]🔍[/yellow] [bold]{name:<20}[/bold] [dim]{url}[/dim]")

        if notfound:
            console.print(f"\n  [dim]Not found on: {', '.join(notfound[:15])}{'...' if len(notfound)>15 else ''}[/dim]")

        console.print(f"\n  [bold cyan]Total found:[/bold cyan] {len(found)} websites + {len(discord_results)} Discord sources + {len(search_results)} search engines")
        pause()


def email_header_analyzer():
    import re
    while True:
        header("Email Header Analyzer", "Paste raw email headers to analyze")
        console.print("  [dim]Paste your raw email headers below.[/dim]")
        console.print("  [dim]Type END on a new line when done. B to go back.[/dim]\n")

        lines = []
        while True:
            try:
                line = input("  ")
            except (EOFError, KeyboardInterrupt):
                return
            if line.strip().upper() == "END":
                break
            if line.strip().lower() == "b" and not lines:
                return
            lines.append(line)

        raw = "\n".join(lines)
        if not raw.strip():
            continue

        header("Email Header Analyzer", "Results")

        def extract(pattern, text, flags=re.IGNORECASE|re.MULTILINE):
            m = re.search(pattern, text, flags)
            return m.group(1).strip() if m else ""

        t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
        t.add_column("Field",  style="bold cyan", width=22)
        t.add_column("Value",  style="white",     width=54)

        fields = [
            ("From",          extract(r"^From:\s*(.+)$", raw)),
            ("To",            extract(r"^To:\s*(.+)$", raw)),
            ("Subject",       extract(r"^Subject:\s*(.+)$", raw)),
            ("Date",          extract(r"^Date:\s*(.+)$", raw)),
            ("Reply-To",      extract(r"^Reply-To:\s*(.+)$", raw)),
            ("Message-ID",    extract(r"^Message-ID:\s*(.+)$", raw)),
            ("X-Mailer",      extract(r"^X-Mailer:\s*(.+)$", raw)),
            ("X-Originating-IP", extract(r"X-Originating-IP:\s*\[?([0-9.]+)\]?", raw)),
            ("Return-Path",   extract(r"^Return-Path:\s*(.+)$", raw)),
            ("MIME-Version",  extract(r"^MIME-Version:\s*(.+)$", raw)),
        ]
        for k, v in fields:
            if v: t.add_row(k, v[:53])
        console.print(t)

        console.print("\n  [bold]Received Hops (mail path):[/bold]")
        received = re.findall(r"^Received:.*$", raw, re.IGNORECASE|re.MULTILINE)
        ips_seen = set()
        for i, rec in enumerate(received, 1):
            ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", rec)
            for ip in ips:
                if ip not in ips_seen and not ip.startswith(("10.","192.168.","172.")):
                    ips_seen.add(ip)
                    console.print(f"    Hop {i}: [cyan]{ip}[/cyan]", end="")
                    geo = http_json(f"http://ip-api.com/json/{ip}?fields=country,city,isp")
                    if geo and geo.get("status") == "success":
                        console.print(f"  →  {geo.get('city','')}, {geo.get('country','')}  [{geo.get('isp','')}]")
                    else:
                        console.print()

        console.print("\n  [bold]Authentication:[/bold]")
        auth_results = extract(r"^Authentication-Results:\s*(.+)$", raw)
        if auth_results:
            for check in ["spf","dkim","dmarc"]:
                m = re.search(rf"{check}=(\w+)", auth_results, re.IGNORECASE)
                if m:
                    result = m.group(1)
                    col    = "green" if result == "pass" else "red"
                    console.print(f"    {check.upper()}: [{col}]{result}[/{col}]")
        else:
            console.print("  [dim]No Authentication-Results header found.[/dim]")

        console.print("\n  [bold]Spam Indicators:[/bold]")
        spam_score = 0
        checks = [
            ("From ≠ Reply-To",      bool(extract(r"^From:\s*(.+)$", raw)) and
                                     bool(extract(r"^Reply-To:\s*(.+)$", raw)) and
                                     extract(r"^From:\s*(.+)$", raw) != extract(r"^Reply-To:\s*(.+)$", raw)),
            ("No DKIM",              "dkim=pass" not in raw.lower()),
            ("No SPF pass",          "spf=pass" not in raw.lower()),
            ("X-Spam header present",bool(re.search(r"X-Spam", raw, re.I))),
            ("Suspicious X-Mailer",  bool(re.search(r"X-Mailer.*php|X-Mailer.*mass", raw, re.I))),
        ]
        for desc, flag in checks:
            col = "red" if flag else "green"
            mark = "!" if flag else "✓"
            console.print(f"    [{col}]{mark}[/{col}] {desc}")
            if flag: spam_score += 1
        console.print(f"\n  Spam score: [{'red' if spam_score>=3 else 'yellow' if spam_score>=2 else 'green'}]{spam_score}/5[/]")

        pause()


def phone_lookup():
    while True:
        header("Phone Number Lookup", "Deep search: country info, carrier, breach databases, & web profiles")
        console.print("  [dim]Enter a phone number with country code, e.g. +14155552671[/dim]\n")
        number = ask("Phone number (B=back)").strip()
        if number.lower() in ("b",""): return

        import re
        digits = re.sub(r"[^\d+]", "", number)
        if not digits.startswith("+"): digits = "+" + digits

        console.print(f"\n  [yellow]Deep scanning {digits}...[/yellow]\n")

        CC = {
            "1":"USA/Canada","7":"Russia/Kazakhstan","20":"Egypt","27":"South Africa",
            "30":"Greece","31":"Netherlands","32":"Belgium","33":"France","34":"Spain",
            "36":"Hungary","39":"Italy","40":"Romania","41":"Switzerland","43":"Austria",
            "44":"United Kingdom","45":"Denmark","46":"Sweden","47":"Norway","48":"Poland",
            "49":"Germany","51":"Peru","52":"Mexico","53":"Cuba","54":"Argentina",
            "55":"Brazil","56":"Chile","57":"Colombia","58":"Venezuela","60":"Malaysia",
            "61":"Australia","62":"Indonesia","63":"Philippines","64":"New Zealand",
            "65":"Singapore","66":"Thailand","81":"Japan","82":"South Korea","84":"Vietnam",
            "86":"China","90":"Turkey","91":"India","92":"Pakistan","93":"Afghanistan",
            "94":"Sri Lanka","95":"Myanmar","98":"Iran","212":"Morocco","213":"Algeria",
            "234":"Nigeria","254":"Kenya","880":"Bangladesh","886":"Taiwan","971":"UAE",
            "972":"Israel","974":"Qatar","977":"Nepal",
        }

        t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
        t.add_column("Field",  style="bold cyan", width=22)
        t.add_column("Value",  style="white",     width=44)

        cc_found = ""
        cc_name  = ""
        for length in [3,2,1]:
            cc_test = digits[1:1+length]
            if cc_test in CC:
                cc_found = cc_test
                cc_name  = CC[cc_test]
                break

        local = digits[1+len(cc_found):]
        ntype = "Unknown"
        if cc_found == "1":
            if len(local) == 10: ntype = "US/Canada landline or mobile"
            if local.startswith("800") or local.startswith("888"): ntype = "Toll-free"
        elif cc_found == "44":
            if local.startswith("7"): ntype = "UK Mobile"
            elif local.startswith("1") or local.startswith("2"): ntype = "UK Landline"
        elif cc_found == "61":
            if local.startswith("4"): ntype = "Australian Mobile"
            else: ntype = "Australian Landline"

        t.add_row("Number",       digits)
        t.add_row("Country Code", f"+{cc_found} ({cc_name})" if cc_found else "Unknown")
        t.add_row("Local Number", local if local else digits)
        t.add_row("Length",       f"{len(local)} digits local")
        t.add_row("Type",         ntype)
        t.add_row("Valid Format", "[green]Yes[/green]" if 7 <= len(local) <= 12 else "[red]Possibly invalid[/red]")
        console.print(t)

        console.print("\n  [bold cyan]Carrier & Location Info:[/bold cyan]")
        with Progress(SpinnerColumn(), TextColumn("[cyan]Checking APIs...[/cyan]"), console=console) as prog:
            prog.add_task("Search...")

        apis_checked = 0
        carrier_found = False
        
        data = http_json(f"https://phonevalidation.abstractapi.com/v1/?api_key=&phone={digits}")
        if data and data.get("phone"):
            apis_checked += 1
            if data.get("country"): console.print(f"    Country: [cyan]{data['country'].get('name','')}[/cyan]")
            if data.get("location"): console.print(f"    Location: [cyan]{data['location']}[/cyan]")
            if data.get("carrier"): 
                console.print(f"    Carrier: [cyan]{data['carrier']}[/cyan]")
                carrier_found = True
            if data.get("line_type"): console.print(f"    Line type: [cyan]{data['line_type']}[/cyan]")

        console.print(f"\n  [bold yellow]Searching Phone Databases & Web Profiles:[/bold yellow]")
        
        db_sources = [
            ("WhitePages Directory", f"https://www.whitepages.com/search/Reverse-Phone?full_phone={digits}"),
            ("TrueCaller", f"https://www.truecaller.com/search/us/{digits.replace('+','')}"),
            ("SpyDialer", f"https://www.spydialer.com/number.php?Number={digits}"),
            ("CallerID Test", f"https://www.calleridtest.com/"),
            ("SleutheGO Reverse", f"https://www.sleuthego.com/reverse-phone-lookup/"),
            ("NumberGuard", f"https://www.numberguard.com/number/{digits}"),
            ("AnyWho", f"https://www.anywho.com/"),
            ("USA People Finder", f"https://www.usa-people-search.com/"),
        ]

        console.print(f"  [dim]Sources that may contain this number:[/dim]\n")
        for source_name, url in db_sources:
            console.print(f"    [cyan]→[/cyan] [bold]{source_name:<25}[/bold]  [dim]{url}[/dim]")

        console.print(f"\n  [bold red]Data Breach Check:[/bold red]")
        breach_sources = [
            ("HaveIBeenPwned", f"https://haveibeenpwned.com/"),
            ("Data.Breach Index", f"https://www.databreachindex.com/"),
            ("Breach.lol", f"https://breach.lol/"),
            ("LeakCheck API", f"https://leakcheck.io/"),
        ]
        console.print(f"  [dim]Check if this number appears in known breaches:[/dim]\n")
        for source, url in breach_sources:
            console.print(f"    [red]⚠[/red]  [bold]{source:<20}[/bold]  [dim]{url}[/dim]")

        console.print(f"\n  [bold magenta]Social Media & Web Search:[/bold magenta]")
        enc = urllib.parse.quote(digits)
        search_links = [
            ("Google Search", f"https://www.google.com/search?q={enc}"),
            ("Bing Search", f"https://www.bing.com/search?q={enc}"),
            ("Instagram Search", f"https://www.instagram.com/explore/search/keyword/?q={enc}"),
            ("Discord Member Search", f"https://discordapp.com/api/v9/users"),
            ("Telegram Mobile Search", f"https://t.me/search?q={enc}"),
            ("Reddit Search", f"https://www.reddit.com/search/?q={enc}"),
        ]

        for name, link in search_links:
            console.print(f"    [magenta]◆[/magenta] [bold]{name:<25}[/bold] [dim]{link}[/dim]")

        if not carrier_found:
            console.print(f"\n  [dim]💡 Tip: Full carrier/owner lookup requires paid services like TrueCaller, WhitePages Premium, or Spokeo[/dim]")

        pause()


def ssl_checker():
    import ssl as ssl_mod
    while True:
        header("SSL Certificate Checker")
        host = ask("Domain to check (B=back)").strip().lower()
        if host in ("b",""): return
        host = host.replace("https://","").replace("http://","").split("/")[0]

        console.print(f"\n  [yellow]Checking SSL for {host}...[/yellow]\n")
        try:
            ctx  = ssl_mod.create_default_context()
            conn = ctx.wrap_socket(socket.create_connection((host,443), timeout=5), server_hostname=host)
            cert = conn.getpeercert()
            conn.close()

            t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
            t.add_column("Field",  style="bold cyan", width=22)
            t.add_column("Value",  style="white",     width=52)

            subject = dict(x[0] for x in cert.get("subject",[]))
            issuer  = dict(x[0] for x in cert.get("issuer",[]))
            not_before = cert.get("notBefore","")
            not_after  = cert.get("notAfter","")
            sans       = [v for t2,v in cert.get("subjectAltName",[]) if t2=="DNS"]

            try:
                from datetime import datetime as dt
                exp    = dt.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days   = (exp - dt.now()).days
                exp_col= "green" if days > 30 else "yellow" if days > 7 else "red"
                exp_str= f"{not_after}  [{exp_col}]{days} days left[/{exp_col}]"
            except:
                exp_str = not_after

            t.add_row("Host",           host)
            t.add_row("Common Name",    subject.get("commonName",""))
            t.add_row("Organization",   subject.get("organizationName",""))
            t.add_row("Issuer",         issuer.get("organizationName",""))
            t.add_row("Issuer CN",      issuer.get("commonName",""))
            t.add_row("Valid From",     not_before)
            t.add_row("Valid Until",    exp_str)
            t.add_row("Protocol",       conn.version() if hasattr(conn,"version") else "TLS")
            t.add_row("SANs",           "\n".join(sans[:8]) if sans else "")
            console.print(t)

        except ssl_mod.SSLCertVerificationError as e:
            console.print(f"  [red]SSL Error: {e}[/red]")
        except Exception as e:
            console.print(f"  [red]Failed: {e}[/red]")

        pause()



COMMON_SUBDOMAINS = [
    "www","mail","ftp","smtp","pop","pop3","imap","webmail","cpanel","whm",
    "admin","administrator","portal","login","secure","vpn","remote","rdp",
    "api","api2","v1","v2","dev","staging","test","beta","alpha","demo",
    "app","apps","mobile","m","cdn","static","assets","media","img","images",
    "shop","store","blog","news","support","help","docs","wiki","forum",
    "git","gitlab","github","jenkins","jira","confluence","bitbucket",
    "ns","ns1","ns2","ns3","dns","dns1","dns2","mx","mx1","mx2",
    "cloud","aws","azure","gcp","k8s","docker","prod","production","live",
    "db","database","mysql","sql","mongo","redis","elastic","kibana",
    "ftp","sftp","ssh","telnet","proxy","gateway","firewall","lb",
    "monitor","nagios","grafana","prometheus","zabbix","status",
    "old","backup","bak","new","internal","intranet","extranet",
]

def subdomain_finder():
    while True:
        header("Subdomain Finder", "Enumerate subdomains via DNS brute-force + crt.sh")
        domain = ask("Domain (e.g. example.com) — B to back").strip().lower()
        if domain in ("b", ""): return
        domain = domain.replace("https://","").replace("http://","").split("/")[0]

        found = {}

        console.print(f"\n  [yellow]Querying crt.sh certificate logs...[/yellow]")
        crt_data = http_json(f"https://crt.sh/?q=%.{domain}&output=json", timeout=15)
        if crt_data:
            for entry in crt_data:
                names = entry.get("name_value","").split("\n")
                for n in names:
                    n = n.strip().lstrip("*.")
                    if n.endswith(f".{domain}") or n == domain:
                        found[n] = found.get(n, []) + ["crt.sh"]
            console.print(f"  [green]crt.sh found {len(found)} candidates[/green]")
        else:
            console.print("  [dim]crt.sh unavailable[/dim]")

        console.print(f"  [yellow]DNS brute-force ({len(COMMON_SUBDOMAINS)} subdomains)...[/yellow]")
        dns_found = 0
        with Progress(SpinnerColumn(), BarColumn(),
                      TextColumn("{task.completed}/{task.total}"),
                      TextColumn("[cyan]{task.description}[/cyan]"),
                      console=console) as prog:
            task = prog.add_task("", total=len(COMMON_SUBDOMAINS))
            for sub in COMMON_SUBDOMAINS:
                fqdn = f"{sub}.{domain}"
                prog.update(task, description=f"[dim]{fqdn}[/dim]")
                try:
                    ip = socket.gethostbyname(fqdn)
                    if fqdn not in found:
                        found[fqdn] = []
                    found[fqdn].append(f"DNS:{ip}")
                    dns_found += 1
                except Exception:
                    pass
                prog.advance(task)
        console.print(f"  [green]DNS brute-force found {dns_found} live hosts[/green]")

        header(f"Subdomain Finder — {domain}", f"{len(found)} subdomains found")
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Subdomain",  width=38)
        t.add_column("IP",         width=16)
        t.add_column("Sources",    width=20)
        resolved_count = 0
        for fqdn in sorted(found.keys()):
            ip = ""
            try:
                ip = socket.gethostbyname(fqdn)
                resolved_count += 1
                ip_col = "green"
            except:
                ip_col = "dim"
            sources = ", ".join(set(s.split(":")[0] for s in found[fqdn]))
            t.add_row(fqdn, f"[{ip_col}]{ip}[/{ip_col}]", f"[dim]{sources}[/dim]")
        console.print(t)
        console.print(f"\n  [cyan]{len(found)} subdomains found, {resolved_count} resolved to IPs[/cyan]")
        pause()


SERVICE_BANNERS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 5900: "VNC",
    6379: "Redis", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 8888: "Jupyter",
    27017: "MongoDB", 9200: "Elasticsearch", 11211: "Memcached",
    1433: "MSSQL", 1521: "Oracle", 2375: "Docker", 2376: "Docker-TLS",
    6443: "Kubernetes", 10250: "Kubelet", 4444: "Metasploit",
    873: "Rsync", 111: "RPC", 135: "MSRPC", 137: "NetBIOS",
    139: "NetBIOS-SSN", 161: "SNMP", 389: "LDAP", 636: "LDAPS",
    1080: "SOCKS", 3128: "Squid", 8008: "HTTP-Alt2", 9090: "Cockpit",
    9443: "Alt-HTTPS", 502: "Modbus", 102: "S7", 47808: "BACnet",
}

def grab_banner(host, port, timeout=2):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        if port in (80, 8080, 8008):
            s.send(b"HEAD / HTTP/1.0\r\n\r\n")
        elif port == 25:
            pass
        else:
            s.send(b"\r\n")
        banner = s.recv(256).decode("utf-8", errors="replace").strip()
        s.close()
        return banner[:80]
    except:
        return ""

def port_scanner_advanced():
    while True:
        header("Port Scanner", "Service detection + banner grabbing")
        target = ask("Target host/IP (B=back)").strip()
        if target.lower() in ("b",""): return

        try:
            ip = socket.gethostbyname(target)
            if ip != target:
                console.print(f"  Resolved: [cyan]{target}[/cyan] → [green]{ip}[/green]")
        except:
            console.print(f"  [red]Cannot resolve {target}[/red]"); pause(); continue

        range_sel = numbered_menu("Port Scanner", [
            "Top common ports  (fast, ~40 ports)",
            "Top 1000 ports",
            "Full 1-65535  (slow)",
            "Custom range",
        ])
        if range_sel == -1: continue

        if range_sel == 0:   ports = list(SERVICE_BANNERS.keys())
        elif range_sel == 1: ports = list(range(1, 1001))
        elif range_sel == 2: ports = list(range(1, 65536))
        else:
            try:
                s = int(ask("Start port", "1"))
                e = int(ask("End port",   "1024"))
                ports = list(range(s, e+1))
            except: continue

        timeout_sel = numbered_menu("Port Scanner", ["Fast (0.3s)", "Normal (0.8s)", "Slow/thorough (2s)"])
        timeouts = [0.3, 0.8, 2.0]
        tout = timeouts[timeout_sel] if timeout_sel != -1 else 0.5

        header(f"Port Scanner — {target}", "Scanning...")
        open_ports = []

        import threading
        lock = threading.Lock()

        def check_port(port):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(tout)
                if s.connect_ex((ip, port)) == 0:
                    with lock:
                        open_ports.append(port)
                s.close()
            except Exception:
                pass

        with Progress(SpinnerColumn(), BarColumn(),
                      TextColumn("{task.completed}/{task.total} ports"),
                      TextColumn("[dim]{task.description}[/dim]"),
                      console=console) as prog:
            task  = prog.add_task("", total=len(ports))
            batch = 100
            for i in range(0, len(ports), batch):
                chunk   = ports[i:i+batch]
                threads = [threading.Thread(target=check_port, args=(p,)) for p in chunk]
                for th in threads: th.start()
                for th in threads: th.join()
                prog.update(task, description=f":{chunk[-1]}", advance=len(chunk))

        header(f"Port Scanner — {target}", f"{len(open_ports)} open ports")
        if not open_ports:
            console.print("  [dim]No open ports found.[/dim]"); pause(); continue

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Port",    justify="right", width=7)
        t.add_column("Service", width=16)
        t.add_column("Banner / Info", width=54)

        for port in sorted(open_ports):
            svc    = SERVICE_BANNERS.get(port, "Unknown")
            banner = grab_banner(ip, port)
            col    = "green"
            t.add_row(f"[{col}]{port}[/{col}]", f"[cyan]{svc}[/cyan]",
                      f"[dim]{banner}[/dim]" if banner else "[dim]—[/dim]")
        console.print(t)
        pause()


def breach_checker():
    while True:
        header("Breach & Leak Checker", "Check email/password against known breaches")
        opts = ["Check email via HaveIBeenPwned API",
                "Check password (k-anonymity, safe)",
                "Check domain for breaches",
                "Bulk email check from file"]
        sel = numbered_menu("Breach Checker", opts)
        if sel == -1: return
        header("Breach Checker", opts[sel])

        if sel == 0:
            email = ask("Email address")
            console.print(f"\n  [yellow]Checking {email}...[/yellow]")
            console.print("  [dim]Note: HIBP API requires a key for email lookup.[/dim]")
            console.print("  [dim]Get a free key at haveibeenpwned.com/API/Key[/dim]\n")
            key = ask("HIBP API key (leave blank to skip)")
            if key:
                data = http_json(f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(email)}?truncateResponse=false",
                                 timeout=10)
                try:
                    ctx = ssl.create_default_context()
                    req = urllib.request.Request(
                        f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(email)}",
                        headers={"hibp-api-key": key, "User-Agent": "PCToolkit-OSINT"}
                    )
                    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                        breaches = json.loads(r.read())
                    if breaches:
                        console.print(f"  [bold red]Found in {len(breaches)} breach(es):[/bold red]\n")
                        t = Table(box=box.ROUNDED, header_style="bold cyan")
                        t.add_column("Breach",     width=22)
                        t.add_column("Date",       width=12)
                        t.add_column("Data Types", width=40)
                        for b in breaches:
                            types = ", ".join(b.get("DataClasses",[])[:5])
                            t.add_row(b.get("Name",""), b.get("BreachDate",""), types)
                        console.print(t)
                    else:
                        console.print(f"  [green]No breaches found for {email}[/green]")
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        console.print(f"  [green]Good news — not found in any breach![/green]")
                    elif e.code == 401:
                        console.print("  [red]Invalid API key.[/red]")
                    else:
                        console.print(f"  [red]HTTP {e.code}[/red]")
                except Exception as e:
                    console.print(f"  [red]{e}[/red]")
            else:
                console.print("  [dim]Skipped. Get a key at haveibeenpwned.com/API/Key[/dim]")

        elif sel == 1:
            pwd = ask("Password to check (sent as SHA-1 k-anon prefix — safe)")
            if not pwd: continue
            h    = hashlib.sha1(pwd.encode()).hexdigest().upper()
            prefix, suffix = h[:5], h[5:]
            console.print(f"  [dim]Sending prefix {prefix}... (not the full hash)[/dim]")
            data = http_get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=8)
            if data:
                matches = {line.split(":")[0]: int(line.split(":")[1])
                           for line in data.splitlines() if ":" in line}
                count = matches.get(suffix, 0)
                if count:
                    console.print(f"\n  [bold red]Password found {count:,} times in breaches![/bold red]")
                    console.print("  [red]Do NOT use this password.[/red]")
                else:
                    console.print(f"\n  [bold green]Password not found in any known breach.[/bold green]")
                    console.print("  [dim]Still use unique passwords per site.[/dim]")
            else:
                console.print("  [red]Could not reach HIBP API.[/red]")

        elif sel == 2:
            domain = ask("Domain (e.g. company.com)")
            if not domain: continue
            key = ask("HIBP API key (required for domain search)")
            if not key:
                console.print("  [dim]API key required.[/dim]"); pause(); continue
            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(
                    f"https://haveibeenpwned.com/api/v3/breaches",
                    headers={"hibp-api-key": key, "User-Agent": "PCToolkit"}
                )
                with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                    all_breaches = json.loads(r.read())
                domain_breaches = [b for b in all_breaches
                                   if domain.lower() in b.get("Domain","").lower()]
                if domain_breaches:
                    console.print(f"  [red]{len(domain_breaches)} breach(es) involving {domain}:[/red]\n")
                    t = Table(box=box.ROUNDED, header_style="bold cyan")
                    t.add_column("Breach", width=24)
                    t.add_column("Date",   width=12)
                    t.add_column("Count",  justify="right", width=12)
                    t.add_column("Types",  width=30)
                    for b in domain_breaches:
                        t.add_row(b.get("Name",""), b.get("BreachDate",""),
                                  f"{b.get('PwnCount',0):,}",
                                  ", ".join(b.get("DataClasses",[])[:3]))
                    console.print(t)
                else:
                    console.print(f"  [green]No direct breaches found for {domain}[/green]")
            except Exception as e:
                console.print(f"  [red]{e}[/red]")

        elif sel == 3:
            fpath = ask("Path to .txt file (one email per line)").strip().strip('"')
            if not Path(fpath).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            key = ask("HIBP API key")
            if not key: continue
            emails = Path(fpath).read_text().splitlines()
            emails = [e.strip() for e in emails if "@" in e]
            console.print(f"\n  [yellow]Checking {len(emails)} emails...[/yellow]\n")
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Email",    width=34)
            t.add_column("Status",   width=14)
            t.add_column("Breaches", justify="right", width=10)
            for email in emails[:50]:
                try:
                    ctx = ssl.create_default_context()
                    req = urllib.request.Request(
                        f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(email)}",
                        headers={"hibp-api-key": key, "User-Agent": "PCToolkit"}
                    )
                    with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                        br = json.loads(r.read())
                    t.add_row(email, "[red]BREACHED[/red]", str(len(br)))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        t.add_row(email, "[green]Clean[/green]", "0")
                    else:
                        t.add_row(email, f"[dim]err {e.code}[/dim]", "?")
                except:
                    t.add_row(email, "[dim]error[/dim]", "?")
                time.sleep(1.6)  # HIBP rate limit
            console.print(t)
        pause()


DORK_TEMPLATES = {
    "Find login pages":               'site:{} inurl:login OR inurl:signin OR inurl:admin',
    "Find exposed files":             'site:{} filetype:pdf OR filetype:xls OR filetype:doc',
    "Find config/env files":          'site:{} ext:env OR ext:config OR ext:ini OR ext:cfg',
    "Find SQL/DB dumps":              'site:{} filetype:sql OR filetype:db OR filetype:sqlite',
    "Find exposed directories":       'site:{} intitle:"index of" inurl:{}',
    "Find cameras/webcams":           'site:{} inurl:view/index.shtml OR inurl:ViewerFrame',
    "Find WordPress admin":           'site:{} inurl:wp-admin OR inurl:wp-login.php',
    "Find phpMyAdmin":                'site:{} inurl:phpmyadmin',
    "Find backup files":              'site:{} filetype:bak OR filetype:backup OR filetype:old',
    "Find API keys in JS":            'site:{} ext:js apikey OR api_key OR secret',
    "Find exposed git repos":         'site:{} inurl:.git/config',
    "Find email addresses":           'site:{} "@{}"',
    "Find subdomains":                'site:*.{}',
    "Find error messages":            'site:{} "Warning: mysql_fetch" OR "SQL syntax" OR "error in your SQL"',
    "Find open redirects":            'site:{} inurl:redirect= OR inurl:url= OR inurl:goto=',
    "Find Jira/Confluence":           'site:{} inurl:jira OR inurl:confluence',
    "Find exposed S3 buckets":        '"{}" site:s3.amazonaws.com',
    "Find pastebin leaks":            '"{}" site:pastebin.com',
    "Find LinkedIn employees":        'site:linkedin.com "at {}"',
    "Find cached pages":              'cache:{}',
    "Find related sites":             'related:{}',
}

def google_dorking():
    while True:
        header("Google Dorking Helper", "Build & copy search dorks")
        target = ask("Target domain or keyword (B=back)").strip()
        if target.lower() in ("b",""): return

        console.print(f"\n  [bold]Generated dorks for: [cyan]{target}[/cyan][/bold]\n")
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",        width=4)
        t.add_column("Purpose",  width=28)
        t.add_column("Dork Query", width=52)

        dork_list = list(DORK_TEMPLATES.items())
        for i, (purpose, template) in enumerate(dork_list, 1):
            dork = template.format(target)
            t.add_row(str(i), purpose, f"[dim]{dork[:51]}[/dim]")
        console.print(t)

        console.print("\n  [dim]Enter number to open in browser, A=open all, C=copy one, B=back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            for purpose, template in list(dork_list)[:5]:
                dork = template.format(target)
                url  = f"https://www.google.com/search?q={urllib.parse.quote(dork)}"
                subprocess.Popen(["cmd","/c","start","",url])
                time.sleep(0.3)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(dork_list):
                purpose, template = dork_list[idx]
                dork = template.format(target)
                url  = f"https://www.google.com/search?q={urllib.parse.quote(dork)}"
                subprocess.Popen(["cmd","/c","start","",url])
                console.print(f"  [green]Opened: {dork[:60]}[/green]")
                time.sleep(0.5)


def url_analyzer():
    import re
    while True:
        header("URL Analyzer & Unshortener")
        url = ask("Enter URL to analyze (B=back)").strip()
        if url.lower() in ("b",""): return
        if not url.startswith("http"):
            url = "https://" + url

        console.print(f"\n  [yellow]Analyzing {url}...[/yellow]\n")

        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        t = Table(box=box.ROUNDED, show_header=False)
        t.add_column("Field",  style="bold cyan", width=18)
        t.add_column("Value",  style="white",     width=56)
        t.add_row("Full URL",  url[:72])
        t.add_row("Scheme",    parsed.scheme)
        t.add_row("Domain",    parsed.netloc)
        t.add_row("Path",      parsed.path[:55] or "/")
        t.add_row("Query",     parsed.query[:55])
        t.add_row("Fragment",  parsed.fragment[:55])
        if parsed.query:
            params = parse_qs(parsed.query)
            for k, v in list(params.items())[:5]:
                t.add_row(f"  ?{k}", str(v[0])[:50])
        console.print(t)

        console.print("\n  [bold]Redirect Chain:[/bold]")
        current = url
        chain   = [url]
        for _ in range(10):
            try:
                req = urllib.request.Request(
                    current,
                    headers={"User-Agent": "Mozilla/5.0"},
                    method="HEAD"
                )
                opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
                class NoRedirect(urllib.request.HTTPErrorProcessor):
                    def http_response(self, req, response): return response
                    https_response = http_response

                opener2 = urllib.request.build_opener(NoRedirect)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with opener2.open(current, timeout=5) as r:
                    code = r.status
                    loc  = r.headers.get("Location","")
                if code in (301,302,303,307,308) and loc:
                    if loc.startswith("/"): loc = f"{parsed.scheme}://{parsed.netloc}{loc}"
                    console.print(f"    [{code}] [dim]{current[:55]}[/dim]")
                    console.print(f"       → [cyan]{loc[:55]}[/cyan]")
                    chain.append(loc)
                    current = loc
                else:
                    console.print(f"    [{code}] [green]{current[:60]}[/green]  (final)")
                    break
            except Exception as e:
                console.print(f"    [dim]{str(e)[:60]}[/dim]")
                break

        final_domain = urlparse(current).netloc

        console.print(f"\n  [bold]Final destination:[/bold] [cyan]{current[:70]}[/cyan]")
        try:
            final_ip = socket.gethostbyname(final_domain)
            console.print(f"  [bold]Resolved IP:[/bold] [cyan]{final_ip}[/cyan]")
            geo = http_json(f"http://ip-api.com/json/{final_ip}?fields=country,city,isp,org,proxy,hosting")
            if geo and geo.get("status") == "success":
                console.print(f"  Location: {geo.get('city','')}, {geo.get('country','')}")
                console.print(f"  ISP: {geo.get('org','')}")
                if geo.get("proxy"):   console.print("  [red]! Proxy/VPN detected[/red]")
                if geo.get("hosting"): console.print("  [yellow]! Hosting/datacenter IP[/yellow]")
        except Exception:
            pass

        console.print("\n  [bold]Safety Checks:[/bold]")
        flags = []
        if len(chain) > 3:         flags.append(("yellow","Multiple redirects — could be cloaking"))
        if any(c.isdigit() for c in parsed.netloc.split(".")[0]):
            flags.append(("yellow","IP-like hostname"))
        if parsed.netloc.count(".") > 4:
            flags.append(("yellow","Many subdomains — possible phishing"))
        suspicious_tlds = [".tk",".ml",".ga",".cf",".gq",".xyz",".top",".click",".loan"]
        if any(parsed.netloc.endswith(t) for t in suspicious_tlds):
            flags.append(("red","Suspicious TLD"))
        if "bit.ly" in url or "t.co" in url or "tinyurl" in url or "goo.gl" in url:
            flags.append(("yellow","URL shortener used"))
        if len(parsed.path) > 80: flags.append(("yellow","Very long path"))
        if flags:
            for col, msg in flags:
                console.print(f"  [{col}]! {msg}[/{col}]")
        else:
            console.print("  [green]No obvious red flags detected[/green]")

        pause()


def mac_lookup():
    while True:
        header("MAC Address Lookup", "Identify vendor from MAC address")

        console.print("  [bold]Your network interfaces:[/bold]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        t.add_column("Interface", width=24)
        t.add_column("MAC",       width=20)
        t.add_column("IP",        width=18)
        for iface, addrs in psutil.net_if_addrs().items():
            mac = next((a.address for a in addrs if a.family == psutil.AF_LINK), "")
            ip  = next((a.address for a in addrs if a.family == socket.AF_INET), "")
            if mac: t.add_row(iface[:23], mac, ip)
        console.print(t)
        console.print()

        mac = ask("Enter MAC address to lookup (B=back)").strip()
        if mac.lower() in ("b",""): return

        mac_clean = mac.replace("-","").replace(":","").replace(".","").upper()
        if len(mac_clean) < 6:
            console.print("  [red]Invalid MAC address.[/red]"); pause(); continue
        oui = mac_clean[:6]
        oui_fmt = f"{oui[:2]}:{oui[2:4]}:{oui[4:6]}"

        console.print(f"\n  [yellow]Looking up OUI {oui_fmt}...[/yellow]\n")

        data = http_get(f"https://api.macvendors.com/{oui_fmt}", timeout=6)
        vendor = data.strip() if data and "errors" not in data.lower() else "Unknown"

        data2 = http_json(f"https://api.maclookup.app/v2/macs/{oui_fmt}", timeout=6)

        t2 = Table(box=box.ROUNDED, show_header=False)
        t2.add_column("Field",  style="bold cyan", width=22)
        t2.add_column("Value",  style="white",     width=44)
        t2.add_row("MAC Address",   mac)
        t2.add_row("OUI",           oui_fmt)
        t2.add_row("Vendor",        vendor)
        if data2:
            t2.add_row("Company",   data2.get("company","") or vendor)
            t2.add_row("Country",   data2.get("country",""))
            t2.add_row("Type",      data2.get("type",""))
            t2.add_row("Private",   "[yellow]Yes[/yellow]" if data2.get("private") else "No")
        console.print(t2)

        console.print("\n  [bold]Analysis:[/bold]")
        first_byte = int(mac_clean[:2], 16)
        if first_byte & 0x01:
            console.print("  [yellow]Multicast MAC address[/yellow]")
        else:
            console.print("  [dim]Unicast MAC address[/dim]")
        if first_byte & 0x02:
            console.print("  [yellow]Locally administered (randomized) — may not reveal real vendor[/yellow]")
        else:
            console.print("  [dim]Globally unique (manufacturer assigned)[/dim]")

        pause()


def tor_vpn_detector():
    while True:
        header("Tor / VPN / Proxy Detector")
        ip = ask("IP to check (leave blank for your own IP, B=back)").strip()
        if ip.lower() == "b": return

        if not ip:
            try:
                ip = http_get("https://api.ipify.org", timeout=5).strip()
                console.print(f"  Your public IP: [cyan]{ip}[/cyan]")
            except:
                console.print("  [red]Could not get public IP[/red]"); pause(); continue

        console.print(f"\n  [yellow]Analyzing {ip}...[/yellow]\n")

        results = {}

        data = http_json(f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as,proxy,hosting,mobile,query")
        if data and data.get("status") == "success":
            results["ip-api proxy flag"]  = data.get("proxy", False)
            results["ip-api hosting flag"] = data.get("hosting", False)
            results["ip-api mobile"]       = data.get("mobile", False)
            results["Country"]  = data.get("country","")
            results["ISP"]      = data.get("isp","")
            results["Org"]      = data.get("org","")
            results["ASN"]      = data.get("as","")

        console.print("  [dim]Checking Tor exit node list...[/dim]")
        tor_list = http_get("https://check.torproject.org/exit-addresses", timeout=8)
        is_tor   = tor_list and ip in tor_list if tor_list else False

        data2 = http_json(f"https://ipinfo.io/{ip}/json", timeout=6)
        is_vpn_org = False
        if data2:
            org = data2.get("org","").lower()
            vpn_keywords = ["vpn","proxy","hosting","cloud","digitalocean","linode",
                            "vultr","hetzner","ovh","tor","mullvad","nordvpn","expressvpn",
                            "surfshark","proton","windscribe","privateinternetaccess"]
            is_vpn_org = any(kw in org for kw in vpn_keywords)

        abuse_data = http_json(f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}", timeout=5)

        t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
        t.add_column("Check",   style="bold cyan", width=28)
        t.add_column("Result",  style="white",     width=36)

        def yn(val):
            return "[red]YES[/red]" if val else "[green]No[/green]"

        t.add_row("IP",             ip)
        t.add_row("Country",        results.get("Country","?"))
        t.add_row("ISP",            results.get("ISP","?"))
        t.add_row("Org",            results.get("Org","?"))
        t.add_row("ASN",            results.get("ASN","?"))
        t.add_row("Tor Exit Node",  "[bold red]YES — TOR[/bold red]" if is_tor else "[green]No[/green]")
        t.add_row("Proxy/VPN (ip-api)", yn(results.get("ip-api proxy flag")))
        t.add_row("Datacenter/Host",    yn(results.get("ip-api hosting flag")))
        t.add_row("Mobile Network",     yn(results.get("ip-api mobile")))
        t.add_row("VPN-like Org name",  yn(is_vpn_org))
        console.print(t)

        score = sum([
            bool(is_tor),
            bool(results.get("ip-api proxy flag")),
            bool(results.get("ip-api hosting flag")),
            bool(is_vpn_org),
        ])
        risk_labels = ["Clean","Low","Medium","High","Very High"]
        risk_cols   = ["green","cyan","yellow","red","bold red"]
        risk  = risk_labels[min(score, 4)]
        rcol  = risk_cols[min(score, 4)]
        console.print(f"\n  Risk Score: [{rcol}]{risk} ({score}/4)[/{rcol}]")

        pause()


TECH_SIGNATURES = {
    "WordPress":       [("header","X-Powered-By","WordPress"), ("body","wp-content"), ("body","wp-includes")],
    "Joomla":          [("body","joomla"), ("body","/components/com_")],
    "Drupal":          [("header","X-Generator","Drupal"), ("body","Drupal.settings")],
    "Shopify":         [("body","Shopify.theme"), ("body","cdn.shopify.com")],
    "Wix":             [("body","wix.com"), ("body","wixstatic.com")],
    "Squarespace":     [("body","squarespace.com")],
    "Webflow":         [("body","webflow.com")],
    "React":           [("body","__reactFiber"), ("body","react-root"), ("body","_reactRootContainer")],
    "Next.js":         [("body","__NEXT_DATA__"), ("header","x-powered-by","Next.js")],
    "Angular":         [("body","ng-version"), ("body","ng-app")],
    "Vue.js":          [("body","__vue__"), ("body","data-v-")],
    "jQuery":          [("body","jquery"), ("body","jQuery")],
    "Bootstrap":       [("body","bootstrap.min.css"), ("body","bootstrap.css")],
    "Apache":          [("header","Server","Apache")],
    "Nginx":           [("header","Server","nginx")],
    "IIS":             [("header","Server","Microsoft-IIS")],
    "Cloudflare":      [("header","CF-Ray",None), ("header","Server","cloudflare")],
    "AWS CloudFront":  [("header","Via","CloudFront")],
    "Google Analytics":[("body","google-analytics.com/analytics"), ("body","gtag(")],
    "Google Tag Manager":[("body","googletagmanager.com/gtm")],
    "Hotjar":          [("body","hotjar.com")],
    "Intercom":        [("body","intercom.io")],
    "reCAPTCHA":       [("body","google.com/recaptcha")],
    "Cloudflare WAF":  [("header","CF-Ray",None)],
    "hCaptcha":        [("body","hcaptcha.com")],
    "PHP":             [("header","X-Powered-By","PHP"), ("body",".php")],
    "ASP.NET":         [("header","X-Powered-By","ASP.NET"), ("header","X-AspNet-Version",None)],
    "Ruby on Rails":   [("header","X-Powered-By","Phusion Passenger")],
    "Django":          [("body","csrfmiddlewaretoken")],
    "Laravel":         [("body","laravel_session"), ("header","Set-Cookie","laravel")],
}

def website_fingerprinter():
    while True:
        header("Website Technology Fingerprinter")
        url = ask("Website URL (B=back)").strip()
        if url.lower() in ("b",""): return
        if not url.startswith("http"): url = "https://" + url

        console.print(f"\n  [yellow]Fingerprinting {url}...[/yellow]\n")

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                headers = dict(r.headers)
                body    = r.read(200000).decode("utf-8", errors="replace")
                status  = r.status
        except Exception as e:
            console.print(f"  [red]Failed to fetch: {e}[/red]"); pause(); continue

        detected = {}
        body_lower    = body.lower()
        for tech, sigs in TECH_SIGNATURES.items():
            for sig_type, sig_key, sig_val in sigs:
                if sig_type == "body":
                    if sig_key.lower() in body_lower:
                        detected[tech] = True
                elif sig_type == "header":
                    hval = headers.get(sig_key,"").lower()
                    if sig_val is None and hval:
                        detected[tech] = True
                    elif sig_val and sig_val.lower() in hval:
                        detected[tech] = True

        header(f"Tech Fingerprint — {url[:40]}", f"HTTP {status}")

        cats = {
            "CMS":        ["WordPress","Joomla","Drupal","Shopify","Wix","Squarespace","Webflow"],
            "Framework":  ["React","Next.js","Angular","Vue.js","jQuery","Bootstrap"],
            "Server":     ["Apache","Nginx","IIS","Cloudflare","AWS CloudFront"],
            "Analytics":  ["Google Analytics","Google Tag Manager","Hotjar","Intercom"],
            "Security":   ["reCAPTCHA","Cloudflare WAF","hCaptcha"],
            "Backend":    ["PHP","ASP.NET","Ruby on Rails","Django","Laravel"],
        }
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Category",   width=12)
        t.add_column("Detected",   width=56)
        for cat, techs in cats.items():
            found_in_cat = [t2 for t2 in techs if t2 in detected]
            if found_in_cat:
                t.add_row(f"[cyan]{cat}[/cyan]",
                          "  ".join(f"[green]{t2}[/green]" for t2 in found_in_cat))
        console.print(t)

        console.print("\n  [bold]Response Headers:[/bold]")
        ht = Table(box=box.SIMPLE, show_header=False)
        ht.add_column("Header", style="cyan",  width=28)
        ht.add_column("Value",  style="white", width=46)
        interesting = ["Server","X-Powered-By","X-Frame-Options","Content-Security-Policy",
                       "Strict-Transport-Security","X-XSS-Protection","X-Content-Type-Options",
                       "CF-Ray","Via","Set-Cookie","X-Generator","X-AspNet-Version"]
        for h in interesting:
            val = headers.get(h,"")
            if val: ht.add_row(h, val[:45])
        console.print(ht)

        console.print(f"\n  [bold]Total technologies detected: [cyan]{len(detected)}[/cyan][/bold]")
        pause()


def exif_extractor():
    while True:
        header("Image EXIF / Metadata Extractor")
        path = ask("Image file path (drag & drop — B=back)").strip().strip('"')
        if path.lower() in ("b",""): return

        if not Path(path).exists():
            console.print("  [red]File not found.[/red]"); pause(); continue

        ext = Path(path).suffix.lower()
        console.print(f"\n  [yellow]Reading metadata from {Path(path).name}...[/yellow]\n")

        exiftool = shutil.which("exiftool")
        if exiftool:
            result = subprocess.run([exiftool, path], capture_output=True, text=True)
            if result.returncode == 0:
                t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
                t.add_column("Tag",   style="bold cyan", width=30)
                t.add_column("Value", style="white",     width=46)
                gps_found = False
                for line in result.stdout.splitlines()[:60]:
                    if ":" in line:
                        k, _, v = line.partition(":")
                        k = k.strip(); v = v.strip()
                        if k and v:
                            if "gps" in k.lower(): gps_found = True
                            t.add_row(k[:29], v[:45])
                console.print(t)
                if gps_found:
                    console.print("\n  [bold red]! GPS data found — this image contains location information![/bold red]")
                pause(); continue

        try:
            with open(path, "rb") as f:
                data = f.read(65536)

            size = Path(path).stat().st_size
            t = Table(box=box.ROUNDED, header_style="bold cyan", show_header=False)
            t.add_column("Field",  style="bold cyan", width=24)
            t.add_column("Value",  style="white",     width=48)
            t.add_row("Filename",  Path(path).name)
            t.add_row("Size",      fmt_bytes(size))
            t.add_row("Extension", ext)
            t.add_row("Modified",  datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"))

            if ext in (".jpg",".jpeg"):
                import struct
                exif_pos = data.find(b'\xff\xe1')
                if exif_pos != -1:
                    t.add_row("EXIF Data",    "[yellow]Present[/yellow]")
                    if b'GPS' in data[exif_pos:exif_pos+2000]:
                        t.add_row("GPS Data", "[bold red]Present![/bold red]")
                    for marker in [b'Canon', b'Nikon', b'Sony', b'Apple', b'Samsung',
                                   b'FUJIFILM', b'Olympus', b'Panasonic', b'Leica']:
                        if marker in data:
                            t.add_row("Camera Make", marker.decode())
                            break
                else:
                    t.add_row("EXIF Data", "[dim]Not found[/dim]")

            elif ext == ".png":
                if b'tEXt' in data:
                    t.add_row("PNG Text", "[yellow]Present[/yellow]")
                chunks = [b'tEXt', b'zTXt', b'iTXt', b'cHRM', b'gAMA']
                for chunk in chunks:
                    if chunk in data:
                        pos = data.find(chunk) + 4
                        text = data[pos:pos+100].decode("utf-8", errors="replace").split("\x00")[0]
                        if text.strip(): t.add_row(chunk.decode(), text[:45])

            console.print(t)
            console.print("\n  [dim]Tip: Install ExifTool for full metadata extraction:[/dim]")
            console.print("  [dim]https://exiftool.org[/dim]")

        except Exception as e:
            console.print(f"  [red]Error reading file: {e}[/red]")

        pause()


def packet_sniffer():
    header("Network Packet Sniffer", "Requires Npcap or WinPcap")
    console.print("  [yellow]Checking for packet capture library...[/yellow]\n")

    has_scapy = False

    if not has_scapy:
        console.print("  [dim]Scapy not installed. Options:[/dim]\n")
        opts = [
            "Install scapy  (pip install scapy)",
            "Use netstat live view instead  (no install needed)",
            "Show active connections snapshot",
        ]
        sel = numbered_menu("Packet Sniffer", opts)
        if sel == -1: return

        if sel == 0:
            console.print("  [yellow]Installing scapy...[/yellow]")
            result = subprocess.run([sys.executable,"-m","pip","install","scapy","-q"])
            if result.returncode == 0:
                console.print("  [green]Installed! Also install Npcap from npcap.com[/green]")
                console.print("  [dim]Restart the toolkit then use this tool.[/dim]")
            else:
                console.print("  [red]Install failed.[/red]")
            pause(); return

        elif sel == 1:
            header("Live Connection Monitor", "Press ENTER to stop")
            import threading
            stop = False
            def wait():
                nonlocal stop; input(); stop = True
            threading.Thread(target=wait, daemon=True).start()

            prev = {}
            with Live(console=console, refresh_per_second=2) as live:
                while not stop:
                    conns = psutil.net_connections("inet")
                    io    = psutil.net_io_counters()
                    t = Table(box=box.SIMPLE, header_style="bold cyan")
                    t.add_column("PID",    width=7, justify="right")
                    t.add_column("Proto",  width=5)
                    t.add_column("Local",  width=22)
                    t.add_column("Remote", width=22)
                    t.add_column("State",  width=14)
                    t.add_column("Proc",   width=14)
                    for c in sorted(conns, key=lambda x: x.status)[:20]:
                        try: pname = psutil.Process(c.pid).name()[:13] if c.pid else "?"
                        except: pname = "?"
                        proto = "TCP" if c.type==socket.SOCK_STREAM else "UDP"
                        la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                        ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                        col = "green" if c.status=="ESTABLISHED" else "yellow" if "WAIT" in c.status else "dim"
                        t.add_row(str(c.pid or "?"), proto, la, ra,
                                  f"[{col}]{c.status}[/{col}]", pname)
                    out = (f"  [bold]Net I/O:[/bold] "
                           f"↑ [cyan]{fmt_bytes(io.bytes_sent)}[/cyan]  "
                           f"↓ [green]{fmt_bytes(io.bytes_recv)}[/green]  "
                           f"Err: [red]{io.errin+io.errout}[/red]\n\n")
                    live.update(Panel(Group(out, t),
                                     title="[cyan]Live Connections[/cyan]"))
                    time.sleep(0.5)
                    if stop: break
            return

        elif sel == 2:
            header("Connection Snapshot")
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Proto", width=5)
            t.add_column("Local", width=22)
            t.add_column("Remote",width=22)
            t.add_column("State", width=14)
            t.add_column("PID",   width=7, justify="right")
            t.add_column("Process",width=16)
            for c in psutil.net_connections("inet"):
                try: pname = psutil.Process(c.pid).name()[:15] if c.pid else "?"
                except: pname = "?"
                proto = "TCP" if c.type==socket.SOCK_STREAM else "UDP"
                la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                col = "green" if c.status=="ESTABLISHED" else "dim"
                t.add_row(proto, la, ra, f"[{col}]{c.status}[/{col}]",
                          str(c.pid or "?"), pname)
            console.print(t)
            pause(); return


    pause()


SOCIAL_PLATFORMS = [
    ("GitHub",       "https://github.com/{}",                    ["avatar","repositories","followers"]),
    ("Twitter/X",    "https://twitter.com/{}",                   ["twitter.com/{}","profile"]),
    ("Reddit",       "https://www.reddit.com/user/{}.json",      ["name","link_karma","comment_karma","created_utc","is_gold"]),
    ("TikTok",       "https://www.tiktok.com/@{}",               ["follower","following","likes"]),
    ("Instagram",    "https://www.instagram.com/{}/",            ["follower","following","posts"]),
    ("YouTube",      "https://www.youtube.com/@{}",              ["subscriber","channel"]),
    ("Twitch",       "https://www.twitch.tv/{}",                 ["follower","stream"]),
    ("Steam",        "https://steamcommunity.com/id/{}",         ["games","friends","steam"]),
    ("LinkedIn",     "https://www.linkedin.com/in/{}",           ["linkedin","profile"]),
    ("Pinterest",    "https://www.pinterest.com/{}/",            ["pin","board","follower"]),
    ("DeviantArt",   "https://www.deviantart.com/{}",            ["deviation","watcher"]),
    ("Flickr",       "https://www.flickr.com/people/{}",         ["photo","contact"]),
    ("SoundCloud",   "https://soundcloud.com/{}",                ["track","follower","following"]),
    ("Spotify",      "https://open.spotify.com/user/{}",         ["playlist","follower"]),
    ("Medium",       "https://medium.com/@{}",                   ["follower","story","clap"]),
    ("Substack",     "https://{}.substack.com",                  ["subscriber","post"]),
    ("Patreon",      "https://www.patreon.com/{}",               ["patron","tier","creator"]),
    ("Gitlab",       "https://gitlab.com/{}",                    ["project","commit","merge"]),
    ("Bitbucket",    "https://bitbucket.org/{}",                 ["repository","commit"]),
    ("Replit",       "https://replit.com/@{}",                   ["repl","follower"]),
    ("Keybase",      "https://keybase.io/{}",                    ["public key","proof","follower"]),
    ("HackerNews",   "https://news.ycombinator.com/user?id={}",  ["karma","created","about"]),
    ("Roblox",       "https://www.roblox.com/user.aspx?username={}",["robux","friend","game"]),
    ("Xbox",         "https://xboxgamertag.com/search/{}",       ["gamertag","achievement","game"]),
    ("PSN",          "https://psnprofiles.com/{}",               ["trophy","platinum","game"]),
    ("Twitch",       "https://www.twitch.tv/{}",                 ["follower","stream"]),
    ("Kick",         "https://kick.com/{}",                      ["follower","clip"]),
    ("Discord",      "https://discord.id/?prefill={}",           ["discord","id"]),
    ("Telegram",     "https://t.me/{}",                          ["member","subscriber","view"]),
    ("VK",           "https://vk.com/{}",                        ["friend","subscriber","post"]),
    ("Mastodon",     "https://mastodon.social/@{}",              ["follower","post","toot"]),
]

def social_media_scraper():
    while True:
        header("Social Media Deep Scraper", f"Checks {len(SOCIAL_PLATFORMS)} platforms")
        username = ask("Username (B=back)").strip()
        if username.lower() in ("b",""): return

        console.print(f"\n  [yellow]Scanning '{username}' across {len(SOCIAL_PLATFORMS)} platforms...[/yellow]\n")

        found    = []
        notfound = []
        errors   = []

        with Progress(SpinnerColumn(), BarColumn(),
                      TextColumn("{task.completed}/{task.total}"),
                      TextColumn("[dim]{task.description}[/dim]"),
                      console=console) as prog:
            task = prog.add_task("", total=len(SOCIAL_PLATFORMS))
            for platform, url_tmpl, indicators in SOCIAL_PLATFORMS:
                url = url_tmpl.format(username)
                prog.update(task, description=f"{platform:<16}")
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode    = ssl.CERT_NONE
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"}
                    )
                    with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
                        code = r.status
                        body = r.read(8000).decode("utf-8","replace").lower()
                        if code == 200:
                            indicator_hits = sum(1 for ind in indicators if ind.lower() in body)
                            if indicator_hits >= 1:
                                found.append((platform, url, indicator_hits))
                            else:
                                notfound.append(platform)
                        else:
                            notfound.append(platform)
                except urllib.error.HTTPError as e:
                    if e.code == 404: notfound.append(platform)
                    else: errors.append(f"{platform}({e.code})")
                except Exception as e:
                    errors.append(f"{platform}")
                prog.advance(task)

        header(f"Social Scan — '{username}'", f"{len(found)} found / {len(notfound)} not found")

        if found:
            console.print(f"  [bold green]Found on {len(found)} platform(s):[/bold green]\n")
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Platform",   width=16)
            t.add_column("URL",        width=50)
            t.add_column("Confidence", width=12)
            for platform, url, hits in sorted(found, key=lambda x: x[2], reverse=True):
                conf = "High" if hits>=2 else "Medium"
                col  = "green" if hits>=2 else "yellow"
                t.add_row(f"[green]{platform}[/green]", f"[dim]{url}[/dim]",
                          f"[{col}]{conf}[/{col}]")
            console.print(t)

        if notfound:
            console.print(f"\n  [dim]Not found ({len(notfound)}): {', '.join(notfound[:15])}{'...' if len(notfound)>15 else ''}[/dim]")
        if errors:
            console.print(f"  [dim]Errors: {', '.join(errors[:10])}[/dim]")

        reddit_found = next((f for f in found if f[0]=="Reddit"), None)
        if reddit_found:
            console.print(f"\n  [bold]Reddit Profile Data:[/bold]")
            data = http_json(f"https://www.reddit.com/user/{username}/about.json",timeout=8)
            if data and data.get("data"):
                d = data["data"]
                rt = Table(box=box.SIMPLE, show_header=False)
                rt.add_column("k", style="cyan", width=18)
                rt.add_column("v", style="white", width=30)
                rt.add_row("Karma (link)",    str(d.get("link_karma","")))
                rt.add_row("Karma (comment)", str(d.get("comment_karma","")))
                rt.add_row("Account created", datetime.fromtimestamp(d.get("created_utc",0)).strftime("%Y-%m-%d"))
                rt.add_row("Gold",           "[yellow]Yes[/yellow]" if d.get("is_gold") else "No")
                rt.add_row("Verified",       "[green]Yes[/green]" if d.get("verified") else "No")
                rt.add_row("NSFW",           "[red]Yes[/red]" if d.get("over_18") else "No")
                console.print(rt)

        pause()


def darkweb_checker():
    while True:
        header("Dark Web Mention Checker", "Search public leak indexes & paste sites")
        console.print("  [dim]Searches publicly indexed leak databases, paste sites,[/dim]")
        console.print("  [dim]and dark web surface indexes. Does NOT access .onion sites.[/dim]\n")

        query = ask("Search query (email/username/domain/keyword — B=back)").strip()
        if query.lower() in ("b",""): return

        console.print(f"\n  [yellow]Searching for '{query}'...[/yellow]\n")

        sources_checked = []
        mentions        = []

        dork1 = f'"{query}" site:pastebin.com'
        dork2 = f'"{query}" site:ghostbin.com OR site:privatebin.net OR site:hastebin.com'
        dork3 = f'"{query}" "leaked" OR "breach" OR "dump" OR "hack" OR "database"'

        mentions.append(("Google Dork — Pastebin",
                         f"https://www.google.com/search?q={urllib.parse.quote(dork1)}"))
        mentions.append(("Google Dork — Paste Sites",
                         f"https://www.google.com/search?q={urllib.parse.quote(dork2)}"))
        mentions.append(("Google Dork — Leak Keywords",
                         f"https://www.google.com/search?q={urllib.parse.quote(dork3)}"))
        sources_checked.append("Google dorking")

        console.print("  [dim]Querying IntelligenceX...[/dim]")
        try:
            intelx_resp = http_json(
                f"https://2.intelx.io:443/phonebook/search?term={urllib.parse.quote(query)}&maxresults=10&media=0&target=0&timeout=20&datefrom=&dateto=&sort=2&terminate=[]&sidfilter=[]",
                timeout=10
            )
            if intelx_resp and intelx_resp.get("selectors"):
                for item in intelx_resp["selectors"][:5]:
                    val = item.get("selectvalue","")
                    if val:
                        mentions.append((f"IntelX: {item.get('selectortype','')}",
                                         f"https://intelx.io/?s={urllib.parse.quote(val)}"))
            sources_checked.append("IntelligenceX")
        except Exception:
            pass

        console.print("  [dim]Checking Leak-Lookup...[/dim]")
        try:
            ll_data = http_json(f"https://leak-lookup.com/api/search?key=undefined&type=email_address&query={urllib.parse.quote(query)}", timeout=8)
            if ll_data and ll_data.get("message"):
                for source in ll_data["message"][:5]:
                    mentions.append((f"Leak-Lookup: {source}", "https://leak-lookup.com"))
            sources_checked.append("Leak-Lookup")
        except Exception:
            pass

        mentions.append(("DeHashed Search",
                         f"https://www.dehashed.com/search?query={urllib.parse.quote(query)}"))
        mentions.append(("BreachDirectory",
                         f"https://breachdirectory.org/?type=email&value={urllib.parse.quote(query)}"))
        mentions.append(("Snusbase",
                         f"https://snusbase.com/"))
        mentions.append(("HaveIBeenPwned",
                         f"https://haveibeenpwned.com/account/{urllib.parse.quote(query)}"))
        sources_checked.append("Public leak DBs")

        console.print("  [dim]Searching paste sites...[/dim]")
        paste_hits = []
        for base_url in [
            f"https://pastebin.com/search?q={urllib.parse.quote(query)}",
        ]:
            data = http_get(base_url, timeout=8)
            if data and query.lower() in data.lower():
                import re
                links = re.findall(r'href="(/[A-Za-z0-9]{8})"', data)
                for link in links[:3]:
                    paste_hits.append(f"https://pastebin.com{link}")
        sources_checked.append("Pastebin")

        header(f"Dark Web Check — '{query}'")
        console.print(f"  [bold]Sources checked:[/bold] [dim]{', '.join(sources_checked)}[/dim]\n")

        if paste_hits:
            console.print(f"  [bold red]! Found on Pastebin ({len(paste_hits)} paste(s)):[/bold red]")
            for url in paste_hits:
                console.print(f"    [red]{url}[/red]")
            console.print()

        console.print("  [bold]Search Links (open manually):[/bold]")
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",       width=4)
        t.add_column("Source",  width=28)
        t.add_column("URL",     width=48)
        for i, (source, url) in enumerate(mentions, 1):
            t.add_row(str(i), source, f"[dim]{url[:47]}[/dim]")
        console.print(t)

        console.print("\n  [dim]Enter number to open in browser, or B to go back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b": continue
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(mentions):
                _, url = mentions[idx]
                subprocess.Popen(["cmd","/c","start","",url])
                console.print(f"  [green]Opened in browser.[/green]")
                time.sleep(0.5)
        else:
            break


def geolocation_tracker():
    while True:
        header("Geolocation Tracker", "IP, coordinates, and mapping")
        opts = [
            "Geolocate an IP address",
            "Geolocate a domain",
            "Trace your own location",
            "Bulk IP geolocation from file",
        ]
        sel = numbered_menu("Geolocation", opts)
        if sel == -1: return
        header("Geolocation", opts[sel])

        if sel in (0, 1):
            target = ask("IP or domain")
            if not target: continue
            if sel == 1:
                try: target = socket.gethostbyname(target)
                except: console.print("  [red]Could not resolve.[/red]"); pause(); continue
        elif sel == 2:
            try:
                target = http_get("https://api.ipify.org", timeout=5).strip()
                console.print(f"  Your IP: [cyan]{target}[/cyan]")
            except:
                console.print("  [red]Could not get IP.[/red]"); pause(); continue
        elif sel == 3:
            fpath = ask("File path (one IP per line)").strip().strip('"')
            if not Path(fpath).exists():
                console.print("  [red]Not found.[/red]"); pause(); continue
            ips = [l.strip() for l in Path(fpath).read_text().splitlines() if l.strip()]
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("IP",       width=16)
            t.add_column("Country",  width=14)
            t.add_column("City",     width=16)
            t.add_column("ISP",      width=26)
            t.add_column("Proxy",    width=8)
            for ip in ips[:30]:
                d = http_json(f"http://ip-api.com/json/{ip}?fields=status,country,city,isp,proxy")
                if d and d.get("status")=="success":
                    t.add_row(ip, d.get("country",""), d.get("city",""),
                              d.get("isp","")[:25],
                              "[red]Y[/red]" if d.get("proxy") else "N")
                else:
                    t.add_row(ip,"?","?","?","?")
                time.sleep(0.2)
            console.print(t); pause(); continue

        data = http_json(f"http://ip-api.com/json/{target}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query,reverse,mobile,proxy,hosting")
        if not data or data.get("status") != "success":
            console.print("  [red]Lookup failed.[/red]"); pause(); continue

        t = Table(box=box.ROUNDED, show_header=False)
        t.add_column("Field",  style="bold cyan", width=20)
        t.add_column("Value",  style="white",     width=46)
        for k, v in [
            ("IP",         data.get("query","")),
            ("Hostname",   data.get("reverse","")),
            ("Country",    f"{data.get('country','')} ({data.get('countryCode','')})"),
            ("Region",     data.get("regionName","")),
            ("City",       data.get("city","")),
            ("ZIP",        data.get("zip","")),
            ("Lat / Lon",  f"{data.get('lat','')} , {data.get('lon','')}"),
            ("Timezone",   data.get("timezone","")),
            ("ISP",        data.get("isp","")),
            ("Org",        data.get("org","")),
            ("ASN",        data.get("as","")),
            ("Mobile",     "[yellow]Yes[/yellow]" if data.get("mobile") else "No"),
            ("Proxy/VPN",  "[red]Yes[/red]" if data.get("proxy") else "No"),
            ("Datacenter", "[yellow]Yes[/yellow]" if data.get("hosting") else "No"),
        ]:
            if v: t.add_row(k, str(v))
        console.print(t)

        lat = data.get("lat"); lon = data.get("lon")
        if lat and lon:
            maps_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=12"
            console.print(f"\n  [dim]Map: {maps_url}[/dim]")
            if confirm("Open in browser?"):
                subprocess.Popen(["cmd","/c","start","",maps_url])
        pause()


def whois_domain_intel():
    while True:
        header("WHOIS & Domain Intelligence")
        domain = ask("Domain (B=back)").strip().lower()
        if domain in ("b",""): return
        domain = domain.replace("https://","").replace("http://","").split("/")[0]

        console.print(f"\n  [yellow]Gathering intel on {domain}...[/yellow]\n")

        whois = http_json(f"https://api.whoisjsonapi.com/whoisserver/WhoisService?domainName={domain}&outputFormat=JSON", timeout=10)
        if whois:
            wr = whois.get("WhoisRecord", {})
            t = Table(box=box.ROUNDED, show_header=False)
            t.add_column("Field",   style="bold cyan", width=22)
            t.add_column("Value",   style="white",     width=50)
            for k, v in [
                ("Domain",          wr.get("domainName","")),
                ("Registrar",       wr.get("registrarName","")),
                ("Created",         wr.get("createdDate","")),
                ("Expires",         wr.get("expiresDate","")),
                ("Updated",         wr.get("updatedDate","")),
                ("Status",          wr.get("status","")),
                ("Name Servers",    ", ".join(wr.get("nameServers",{}).get("hostNames",[])[:4]) if wr.get("nameServers") else ""),
                ("Registrant",      wr.get("registrant",{}).get("organization","") if wr.get("registrant") else ""),
                ("Registrant Email",wr.get("contactEmail","")),
                ("Privacy",         "[yellow]Protected[/yellow]" if "privacy" in str(wr).lower() else "Public"),
            ]:
                if v: t.add_row(k, str(v)[:49])
            console.print(t)
        else:
            console.print("  [dim]WHOIS data unavailable.[/dim]")

        console.print("\n  [bold]Hosting & Infrastructure:[/bold]")
        try:
            ip = socket.gethostbyname(domain)
            geo = http_json(f"http://ip-api.com/json/{ip}?fields=country,city,isp,org,as,hosting")
            ht = Table(box=box.SIMPLE, show_header=False)
            ht.add_column("k", style="cyan", width=16)
            ht.add_column("v", style="white", width=40)
            ht.add_row("IP",        ip)
            if geo and geo.get("status")!="fail":
                ht.add_row("Host",     geo.get("isp",""))
                ht.add_row("Org",      geo.get("org",""))
                ht.add_row("Country",  geo.get("country",""))
                ht.add_row("ASN",      geo.get("as",""))
                ht.add_row("Datacenter","[yellow]Yes[/yellow]" if geo.get("hosting") else "No")
            console.print(ht)
        except Exception:
            pass

        if whois:
            wr = whois.get("WhoisRecord",{})
            created = wr.get("createdDate","")
            if created:
                try:
                    from datetime import datetime as dt
                    for fmt in ["%Y-%m-%dT%H:%M:%SZ","%Y-%m-%d","%d-%b-%Y"]:
                        try:
                            age = (dt.now() - dt.strptime(created[:10], fmt[:8])).days
                            years = age // 365
                            console.print(f"\n  Domain age: [cyan]{years} years, {age%365} days[/cyan]")
                            if years < 1: console.print("  [yellow]! Recently registered — exercise caution[/yellow]")
                            break
                        except Exception:
                            pass
                except Exception:
                    pass

        pause()


def advanced_registry_tweaks():
    while True:
        header("Advanced Registry Optimization", "Fine-tune Windows at the registry level")
        
        ADV_TWEAKS = [
            ("Disable Windows Animation (Explorer)",
             winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "AlwaysShowMenus", 1,
             "Instant menu display without animation"),
            
            ("Increase Context Menu Speed",
             winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", "MenuShowDelay", 0,
             "Removes delay when right-clicking (0ms)"),
            
            ("Disable Aero Shake (minimize windows)",
             winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer", "DisallowShaking", 1,
             "Prevents accidental window minimize"),
            
            ("Disable Thumbnail Preview Delay",
             winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer", "NeverShowExt", 0,
             "Show thumbnails instantly on hover"),
            
            ("Windows Key Disable (accidental presses)",
             winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Services\kbdhid\Parameters", "CrashOnCtrlScroll", 1,
             "Prevents Windows key from freezing"),
            
            ("Disable Large System Cache",
             winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management", "LargeSystemCache", 0,
             "Frees RAM for applications (if RAM > 8GB)"),
            
            ("Minimize Working Set",
             winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia", "MMCSS", 1,
             "Aggressive memory cleanup on system idle"),
            
            ("SMB1 Protocol Disable (security + speed)",
             None, None, None, None,
             "Run: powershell -c 'Disable-WindowsOptionalFeature -FeatureName SMB1Protocol -Online -NoRestart'"),
            
            ("Disable App Suggestions",
             winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SoftLandingEnabled", 0,
             "Stops Suggested apps notifications"),
            
            ("Disable Game Bar (reduces RAM)",
             winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0,
             "Saves ~100MB RAM, disables background recording"),
        ]

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",      width=4)
        t.add_column("Tweak",  width=40)
        t.add_column("Effect", width=24)
        for i, (label, *_) in enumerate(ADV_TWEAKS, 1):
            t.add_row(str(i), label[:39], _[-1][:23] if _ else "")
        console.print(t)
        console.print("\n  [dim]A=apply all safe tweaks   number=toggle   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
            console.print("  [yellow]Applying advanced tweaks...[/yellow]")
            for label, hive, path, name, val, desc in ADV_TWEAKS:
                if hive and path and name:
                    try:
                        set_reg_dword(hive, path, name, val)
                    except Exception:
                        pass
            console.print("  [bold green]Advanced tweaks applied![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(ADV_TWEAKS):
                label, hive, path, name, val, desc = ADV_TWEAKS[idx]
                if hive is None:
                    console.print(f"  [yellow]Manual command required[/yellow]\n  {desc}")
                    pause(); continue
                if not IS_ADMIN: console.print("  [red]Needs Admin.[/red]"); time.sleep(1); continue
                try:
                    cur = get_reg_dword(hive, path, name)
                    new = 0 if cur == val else val
                    set_reg_dword(hive, path, name, new)
                    console.print(f"  [green]Applied.[/green]"); time.sleep(0.5)
                except Exception as e:
                    console.print(f"  [red]{e}[/red]"); time.sleep(1)


def startup_profiler():
    while True:
        header("Boot & Startup Analysis", "See what slows down your boot")
        
        if not IS_ADMIN:
            console.print("  [red]Needs Administrator for boot data access.[/red]")
            pause(); return

        console.print("  [yellow]Analyzing boot sequence...[/yellow]\n")

        boot_data = run_ps(
            "Get-EventLog System -Source EventLog -InstanceId 6009 -Newest 1 -ErrorAction SilentlyContinue | "
            "Select-Object TimeGenerated | ConvertTo-Csv"
        )

        console.print("  [bold]Top startup programs affecting boot:[/bold]\n")
        startup_progs = run_ps(
            "Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | "
            "Select-Object Name,Command | Sort-Object Name | Select-Object -First 20 | ConvertTo-Csv"
        )

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Program",  width=30)
        t.add_column("Command",  width=46)
        for line in startup_progs.splitlines()[1:]:
            try:
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    t.add_row(parts[0][:29], parts[1][:45])
            except Exception:
                pass
        console.print(t)

        console.print("\n  [bold]Slow drivers/services on boot:[/bold]")
        slow = run_ps(
            "Get-WmiObject -Class Win32_SystemDriver -Filter 'State=\"Running\"' -ErrorAction SilentlyContinue | "
            "Select-Object DisplayName,SystemName | Select-Object -First 10"
        )
        if slow:
            console.print(f"[dim]{slow[:400]}[/dim]")
        
        console.print("\n  [bold]Recommendations:[/bold]")
        console.print("  [cyan]1[/cyan] Disable unnecessary startup programs in Startup Manager")
        console.print("  [cyan]2[/cyan] Use Full Optimize for comprehensive boot tweaks")
        console.print("  [cyan]3[/cyan] Check Device Manager for problematic drivers")
        console.print("  [cyan]4[/cyan] Install SSD if using HDD for dramatic improvements")

        pause()


def driver_health_check():
    while True:
        header("Driver Health Check", "Find outdated & problematic drivers")
        
        if not IS_ADMIN:
            console.print("  [red]Needs Administrator.[/red]"); pause(); return

        console.print("  [yellow]Scanning drivers...[/yellow]\n")

        drivers = run_ps(
            "Get-WmiObject Win32_PnPSignedDriver -ErrorAction SilentlyContinue | "
            "Select-Object DeviceName,DriverVersion,Date,Manufacturer | "
            "ConvertTo-Csv -NoTypeInformation"
        )

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Device",       width=30)
        t.add_column("Version",      width=12)
        t.add_column("Date",         width=12)
        t.add_column("Status",       width=10)

        old_count = 0
        from datetime import datetime as dt, timedelta
        cutoff = dt.now() - timedelta(days=365)

        for line in drivers.splitlines()[1:50]:
            try:
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 4:
                    name = parts[0][:29]
                    ver  = parts[1][:11]
                    date_str = parts[2][:10] if parts[2] else "Unknown"
                    mfg  = parts[3][:15]
                    
                    try:
                        driver_date = dt.strptime(date_str, "%Y-%m-%d")
                        age_years = (dt.now() - driver_date).days / 365
                        if age_years > 3:
                            status = "[red]VERY OLD[/red]"
                            old_count += 1
                        elif age_years > 1:
                            status = "[yellow]OLD[/yellow]"
                            old_count += 1
                        else:
                            status = "[green]OK[/green]"
                    except:
                        status = "[dim]?[/dim]"
                    
                    t.add_row(name, ver, date_str, status)
            except Exception:
                pass

        console.print(t)
        console.print(f"\n  [bold]Found {old_count} outdated drivers[/bold]")
        console.print("  [dim]Update critical drivers (GPU, chipset, storage) for best performance[/dim]")
        console.print("  [dim]Visit manufacturers' support pages for latest driver downloads[/dim]")

        pause()


def windows_defender_tuner():
    while True:
        header("Windows Defender Optimization", "Balance security & performance")
        
        if not IS_ADMIN:
            console.print("  [red]Needs Administrator.[/red]"); pause(); return

        exclusions = run_ps(
            "Get-MpPreference | Select-Object -ExpandProperty ExclusionPath"
        )

        DEFENDER_TWEAKS = [
            ("Increase Scan Frequency to LOW (faster)",
             "Set-MpPreference -ScanScheduleQuickScanTime 02:00:00"),
            
            ("Add game folders to exclusions (bypass scanning)",
             "Add-MpPreference -ExclusionPath 'C:\\Games' -ErrorAction SilentlyContinue"),
            
            ("Disable Behavioral Monitoring (aggressive)",
             "Set-MpPreference -DisableBehaviorMonitoring $true"),
            
            ("Disable Real-Time Protection (CAUTION)",
             "Set-MpPreference -DisableRealtimeMonitoring $true"),
            
            ("Reduce Network Inspection (slight speed gain)",
             "Set-MpPreference -DisableNetworkProtectionNotifications $true"),
            
            ("Set Defender to Passive Mode (use 3rd party AV)",
             "Set-MpPreference -MAPSReporting Basic"),
        ]

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",     width=4)
        t.add_column("Tweak", width=50)
        for i, (label, cmd) in enumerate(DEFENDER_TWEAKS, 1):
            t.add_row(str(i), label[:49])
        console.print(t)

        console.print("\n  [dim]Current exclusions:[/dim]")
        if exclusions:
            for exc in exclusions.split("\n")[:5]:
                console.print(f"  [cyan]• {exc}[/cyan]")
        else:
            console.print("  [dim]None[/dim]")

        console.print("\n  [dim]1-6=apply tweak   A=balanced preset   B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "a":
            console.print("  [yellow]Applying balanced Defender settings...[/yellow]")
            run_ps("Set-MpPreference -ScanScheduleQuickScanTime 14:00:00")
            run_ps("Set-MpPreference -DisableBehaviorMonitoring $false")
            console.print("  [green]Applied.[/green]"); time.sleep(0.8)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(DEFENDER_TWEAKS):
                label, cmd = DEFENDER_TWEAKS[idx]
                if "CAUTION" in label or "aggressive" in label.lower():
                    if not confirm(f"Apply? {label}"):
                        continue
                console.print(f"  [yellow]{label}...[/yellow]")
                run_ps(cmd)
                console.print("  [green]Applied.[/green]"); time.sleep(0.5)


def context_menu_cleanup():
    while True:
        header("Context Menu Cleanup", "Remove bloat from right-click menu")
        
        if not IS_ADMIN:
            console.print("  [red]Needs Administrator.[/red]"); pause(); return

        console.print("  [yellow]Scanning context menu entries...[/yellow]\n")

        BLOAT_ENTRIES = [
            ("Share with",                  r"shell\shareafile"),
            ("Print with Photos",           r"shell\photoshop.8BIM0"),
            ("Edit with Paint 3D",          r"shell\editpad3d"),
            ("Scan with Windows Defender",  r"shellex\ContextMenuHandlers\EPP"),
            ("Compile with CoffeeScript",   r"shell\CoffeeScript"),
            ("WinRAR / 7-Zip",              r"shell\WinRAR"),
        ]

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("#",     width=4)
        t.add_column("Entry", width=38)
        t.add_column("Status", width=12)
        for i, (name, path) in enumerate(BLOAT_ENTRIES, 1):
            try:
                key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f".\\{BLOAT_ENTRIES[i-1][1]}")
                status = "[red]FOUND[/red]"
                winreg.CloseKey(key)
            except:
                status = "[green]Not installed[/green]"
            t.add_row(str(i), name[:37], status)
        console.print(t)

        console.print("\n  [dim]Select numbers to remove (comma-separated) or R=remove all found, B=back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b": return
        elif raw == "r":
            console.print("  [yellow]Removing bloat entries...[/yellow]")
            for i, (name, path) in enumerate(BLOAT_ENTRIES):
                try:
                    key_path = f"*\\{path}"
                    key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path, 0, winreg.KEY_WRITE)
                    winreg.DeleteKey(key, path.split("\\")[-1])
                    winreg.CloseKey(key)
                except Exception:
                    pass
            console.print("  [green]Done.[/green]"); time.sleep(0.8)


def text_utilities():
    """Text processing and manipulation tools"""
    while True:
        header("Text Utilities", "Process and transform text")
        
        opts = [
            "Convert Case (UPPER/lower/Title)",
            "Remove Duplicate Lines",
            "Sort Lines (A-Z or reverse)",
            "Count Lines/Words/Characters",
            "Find & Replace in Text",
            "Reverse Text/Lines",
            "Encode/Decode Base64",
            "URL Encode/Decode",
            "Remove Empty Lines",
            "Add Line Numbers",
        ]
        
        sel = numbered_menu("Text Utilities", opts)
        if sel == -1: return
        
        header("Text Utilities", opts[sel])
        
        if sel == 0:  # Convert Case
            text = ask("Enter text (or type 'PASTE' for multi-line)")
            if text.upper() == "PASTE": 
                console.print("  [dim]Paste text below, press CTRL+Z then ENTER when done:[/dim]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    text = "\n".join(lines)
            
            case_sel = numbered_menu("Case Conversion", ["UPPERCASE", "lowercase", "Title Case", "iNVERT cASE"])
            if case_sel == -1: continue
            
            if case_sel == 0: result = text.upper()
            elif case_sel == 1: result = text.lower()
            elif case_sel == 2: result = text.title()
            else: result = text.swapcase()
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]\n{result}\n")
        
        elif sel == 1:  # Remove Duplicates
            text = ask("Enter text with duplicate lines (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    pass
            else:
                lines = text.split("\n")
            
            unique_lines = list(dict.fromkeys(lines))  # Preserves order
            console.print(f"\n  [bold]Original:[/bold] {len(lines)} lines")
            console.print(f"  [bold]Unique:[/bold] {len(unique_lines)} lines")
            console.print(f"  [bold cyan]Result:[/bold cyan]\n")
            for line in unique_lines:
                console.print(f"  {line}")
        
        elif sel == 2:  # Sort Lines
            text = ask("Enter text to sort (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    pass
            else:
                lines = text.split("\n")
            
            reverse = confirm("Sort in reverse (Z-A)?")
            sorted_lines = sorted(lines, reverse=reverse)
            
            console.print(f"\n  [bold cyan]Sorted ({len(sorted_lines)} lines):[/bold cyan]\n")
            for line in sorted_lines:
                console.print(f"  {line}")
        
        elif sel == 3:  # Count
            text = ask("Enter text to analyze (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    text = "\n".join(lines)
            
            lines = text.split("\n")
            words = text.split()
            chars = len(text)
            chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
            
            console.print(f"\n  [bold cyan]Text Statistics:[/bold cyan]")
            console.print(f"  Lines: [yellow]{len(lines)}[/yellow]")
            console.print(f"  Words: [yellow]{len(words)}[/yellow]")
            console.print(f"  Characters (with spaces): [yellow]{chars}[/yellow]")
            console.print(f"  Characters (no spaces): [yellow]{chars_no_spaces}[/yellow]")
        
        elif sel == 4:  # Find & Replace
            text = ask("Enter text (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    text = "\n".join(lines)
            
            find = ask("Find what")
            replace = ask("Replace with")
            case_sensitive = confirm("Case sensitive?")
            
            if not case_sensitive:
                import re
                result = re.sub(re.escape(find), replace, text, flags=re.IGNORECASE)
            else:
                result = text.replace(find, replace)
            
            count = text.count(find) if case_sensitive else text.lower().count(find.lower())
            console.print(f"\n  [bold]Replaced {count} occurrences[/bold]")
            console.print(f"  [bold cyan]Result:[/bold cyan]\n{result}\n")
        
        elif sel == 5:  # Reverse
            text = ask("Enter text to reverse (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    text = "\n".join(lines)
            
            rev_sel = numbered_menu("Reverse", ["Reverse entire text", "Reverse each line", "Reverse line order"])
            if rev_sel == -1: continue
            
            if rev_sel == 0:
                result = text[::-1]
            elif rev_sel == 1:
                result = "\n".join([line[::-1] for line in text.split("\n")])
            else:
                result = "\n".join(reversed(text.split("\n")))
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]\n{result}\n")
        
        elif sel == 6:  # Base64
            mode_sel = numbered_menu("Base64", ["Encode to Base64", "Decode from Base64"])
            if mode_sel == -1: continue
            
            text = ask("Enter text")
            
            if mode_sel == 0:
                import base64
                result = base64.b64encode(text.encode()).decode()
            else:
                import base64
                try:
                    result = base64.b64decode(text.encode()).decode()
                except:
                    console.print("  [red]Invalid Base64 input[/red]")
                    pause()
                    continue
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]\n{result}\n")
        
        elif sel == 7:  # URL Encode/Decode
            mode_sel = numbered_menu("URL Encoding", ["URL Encode", "URL Decode"])
            if mode_sel == -1: continue
            
            text = ask("Enter text")
            
            if mode_sel == 0:
                import urllib.parse
                result = urllib.parse.quote(text)
            else:
                import urllib.parse
                result = urllib.parse.unquote(text)
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]\n{result}\n")
        
        elif sel == 8:  # Remove Empty Lines
            text = ask("Enter text (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    text = "\n".join(lines)
            
            lines = text.split("\n")
            non_empty = [line for line in lines if line.strip()]
            
            console.print(f"\n  [bold]Removed {len(lines) - len(non_empty)} empty lines[/bold]")
            console.print(f"  [bold cyan]Result:[/bold cyan]\n")
            for line in non_empty:
                console.print(f"  {line}")
        
        elif sel == 9:  # Add Line Numbers
            text = ask("Enter text (or type 'PASTE')")
            if text.upper() == "PASTE":
                console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    text = "\n".join(lines)
            
            lines = text.split("\n")
            start = int(ask("Start numbering from", "1"))
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]\n")
            for i, line in enumerate(lines, start):
                console.print(f"  {i:4d} | {line}")
        
        pause()



def json_formatter():
    """Format and validate JSON/XML"""
    while True:
        header("JSON/XML Formatter", "Format and beautify structured data")
        
        opts = [
            "Format JSON (Beautify)",
            "Minify JSON",
            "Validate JSON",
            "Format XML (Beautify)",
        ]
        
        sel = numbered_menu("Formatter", opts)
        if sel == -1: return
        
        header("JSON/XML Formatter", opts[sel])
        
        if sel == 0:  # Format JSON
            json_str = ask("Enter JSON (or type 'PASTE')")
            if json_str.upper() == "PASTE":
                console.print("  [dim]Paste JSON, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    json_str = "\n".join(lines)
            
            try:
                import json
                obj = json.loads(json_str)
                formatted = json.dumps(obj, indent=2, sort_keys=True)
                console.print(f"\n  [bold cyan]Formatted JSON:[/bold cyan]\n")
                console.print(formatted)
            except Exception as e:
                console.print(f"  [red]Invalid JSON: {e}[/red]")
        
        elif sel == 1:  # Minify JSON
            json_str = ask("Enter JSON (or type 'PASTE')")
            if json_str.upper() == "PASTE":
                console.print("  [dim]Paste JSON, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    json_str = "\n".join(lines)
            
            try:
                import json
                obj = json.loads(json_str)
                minified = json.dumps(obj, separators=(',', ':'))
                console.print(f"\n  [bold cyan]Minified JSON:[/bold cyan]\n{minified}\n")
                console.print(f"  [dim]Original: {len(json_str)} chars → Minified: {len(minified)} chars[/dim]")
            except Exception as e:
                console.print(f"  [red]Invalid JSON: {e}[/red]")
        
        elif sel == 2:  # Validate JSON
            json_str = ask("Enter JSON to validate (or type 'PASTE')")
            if json_str.upper() == "PASTE":
                console.print("  [dim]Paste JSON, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    json_str = "\n".join(lines)
            
            try:
                import json
                obj = json.loads(json_str)
                console.print(f"  [green]✓ Valid JSON[/green]")
                console.print(f"  Type: {type(obj).__name__}")
                if isinstance(obj, dict):
                    console.print(f"  Keys: {len(obj)}")
                elif isinstance(obj, list):
                    console.print(f"  Items: {len(obj)}")
            except Exception as e:
                console.print(f"  [red]✗ Invalid JSON[/red]")
                console.print(f"  Error: {e}")
        
        elif sel == 3:  # Format XML
            xml_str = ask("Enter XML (or type 'PASTE')")
            if xml_str.upper() == "PASTE":
                console.print("  [dim]Paste XML, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    xml_str = "\n".join(lines)
            
            try:
                import xml.dom.minidom
                dom = xml.dom.minidom.parseString(xml_str)
                formatted = dom.toprettyxml(indent="  ")
                console.print(f"\n  [bold cyan]Formatted XML:[/bold cyan]\n{formatted}\n")
            except Exception as e:
                console.print(f"  [red]Invalid XML: {e}[/red]")
        
        pause()








def password_generator():
    """Advanced password generator and checker"""
    import secrets
    while True:
        header("Password Generator", "Create strong passwords")
        
        opts = [
            "Generate Strong Password",
            "Generate Passphrase",
            "Check Password Strength",
            "Generate PIN Code",
            "Generate Multiple Passwords",
        ]
        
        sel = numbered_menu("Password Tools", opts)
        if sel == -1: return
        
        header("Password Generator", opts[sel])
        
        if sel == 0:  # Strong Password
            length = int(ask("Password length", "16"))
            
            import string
            password = [
                secrets.choice(string.ascii_uppercase),
                secrets.choice(string.ascii_lowercase),
                secrets.choice(string.digits),
                secrets.choice(string.punctuation),
            ]
            
            all_chars = string.ascii_letters + string.digits + string.punctuation
            password += [secrets.choice(all_chars) for _ in range(length - 4)]
            
            for i in range(len(password) - 1, 0, -1):
                j = secrets.randbelow(i + 1)
                password[i], password[j] = password[j], password[i]
            password = ''.join(password)
            
            console.print(f"\n  [bold cyan]Generated Password:[/bold cyan]")
            console.print(f"  [bold yellow]{password}[/bold yellow]\n")
            console.print(f"  Length: {len(password)} characters")
            console.print(f"  [green]✓ Uppercase • Lowercase • Numbers • Special chars[/green]")
        
        elif sel == 1:  # Passphrase
            word_count = int(ask("Number of words", "4"))
            separator = ask("Word separator", "-")
            
            words = ["correct", "horse", "battery", "staple", "apple", "banana", "cherry", 
                    "dragon", "eagle", "forest", "garden", "house", "island", "jungle",
                    "mountain", "ocean", "planet", "river", "summer", "thunder", "winter"]
            
            passphrase = separator.join(secrets.choice(words) for _ in range(word_count))
            
            console.print(f"\n  [bold cyan]Generated Passphrase:[/bold cyan]")
            console.print(f"  [bold yellow]{passphrase}[/bold yellow]\n")
            console.print(f"  Length: {len(passphrase)} characters")
            console.print(f"  [dim]Easier to remember than random characters[/dim]")
        
        elif sel == 2:  # Check Strength
            password = ask("Enter password to check")
            
            score = 0
            feedback = []
            
            if len(password) >= 8: score += 1
            else: feedback.append("[red]✗ Too short (min 8 chars)[/red]")
            
            if len(password) >= 12: score += 1
            else: feedback.append("[yellow]⚠ Consider 12+ characters[/yellow]")
            
            if any(c.isupper() for c in password): score += 1
            else: feedback.append("[red]✗ No uppercase letters[/red]")
            
            if any(c.islower() for c in password): score += 1
            else: feedback.append("[red]✗ No lowercase letters[/red]")
            
            if any(c.isdigit() for c in password): score += 1
            else: feedback.append("[red]✗ No numbers[/red]")
            
            if any(not c.isalnum() for c in password): score += 1
            else: feedback.append("[yellow]⚠ No special characters[/yellow]")
            
            console.print(f"\n  [bold]Password Strength: ", end="")
            if score <= 2:
                console.print(f"[red]WEAK ({score}/6)[/red][/bold]")
            elif score <= 4:
                console.print(f"[yellow]MODERATE ({score}/6)[/yellow][/bold]")
            else:
                console.print(f"[green]STRONG ({score}/6)[/green][/bold]")
            
            console.print(f"\n  [bold]Feedback:[/bold]")
            for f in feedback:
                console.print(f"  {f}")
            
            if score >= 5:
                console.print(f"  [green]✓ Excellent password![/green]")
        
        elif sel == 3:  # PIN Code
            length = int(ask("PIN length", "4"))
            count = int(ask("How many PINs", "1"))
            
            console.print(f"\n  [bold cyan]Generated PINs:[/bold cyan]\n")
            for _ in range(count):
                pin = ''.join(str(secrets.randbelow(10)) for _ in range(length))
                console.print(f"  [yellow]{pin}[/yellow]")
        
        elif sel == 4:  # Multiple Passwords
            count = int(ask("How many passwords", "5"))
            length = int(ask("Password length", "12"))
            
            import string
            console.print(f"\n  [bold cyan]Generated Passwords:[/bold cyan]\n")
            
            for i in range(count):
                password = [
                    secrets.choice(string.ascii_uppercase),
                    secrets.choice(string.ascii_lowercase),
                    secrets.choice(string.digits),
                    secrets.choice(string.punctuation),
                ]
                all_chars = string.ascii_letters + string.digits + string.punctuation
                password += [secrets.choice(all_chars) for _ in range(length - 4)]
                for k in range(len(password) - 1, 0, -1):
                    j = secrets.randbelow(k + 1)
                    password[k], password[j] = password[j], password[k]
                console.print(f"  {i+1}. [yellow]{''.join(password)}[/yellow]")
        
        pause()


def base_converter():
    """Convert between number bases"""
    while True:
        header("Base Converter", "Convert between numbering systems")
        
        opts = [
            "Decimal to Binary",
            "Decimal to Hexadecimal",
            "Decimal to Octal",
            "Binary to Decimal",
            "Hexadecimal to Decimal",
            "Octal to Decimal",
            "Custom Base Conversion",
        ]
        
        sel = numbered_menu("Base Conversion", opts)
        if sel == -1: return
        
        header("Base Converter", opts[sel])
        
        if sel == 0:  # Dec to Bin
            num = int(ask("Enter decimal number"))
            binary = bin(num)[2:]
            console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
            console.print(f"  Decimal: [yellow]{num}[/yellow]")
            console.print(f"  Binary: [yellow]{binary}[/yellow]")
            console.print(f"  [dim](0b{binary})[/dim]")
        
        elif sel == 1:  # Dec to Hex
            num = int(ask("Enter decimal number"))
            hexadecimal = hex(num)[2:].upper()
            console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
            console.print(f"  Decimal: [yellow]{num}[/yellow]")
            console.print(f"  Hexadecimal: [yellow]{hexadecimal}[/yellow]")
            console.print(f"  [dim](0x{hexadecimal})[/dim]")
        
        elif sel == 2:  # Dec to Oct
            num = int(ask("Enter decimal number"))
            octal = oct(num)[2:]
            console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
            console.print(f"  Decimal: [yellow]{num}[/yellow]")
            console.print(f"  Octal: [yellow]{octal}[/yellow]")
            console.print(f"  [dim](0o{octal})[/dim]")
        
        elif sel == 3:  # Bin to Dec
            binary = ask("Enter binary number (without 0b)")
            try:
                decimal = int(binary, 2)
                console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
                console.print(f"  Binary: [yellow]{binary}[/yellow]")
                console.print(f"  Decimal: [yellow]{decimal}[/yellow]")
            except ValueError:
                console.print("  [red]Invalid binary number[/red]")
        
        elif sel == 4:  # Hex to Dec
            hexadecimal = ask("Enter hexadecimal number (without 0x)")
            try:
                decimal = int(hexadecimal, 16)
                console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
                console.print(f"  Hexadecimal: [yellow]{hexadecimal.upper()}[/yellow]")
                console.print(f"  Decimal: [yellow]{decimal}[/yellow]")
            except ValueError:
                console.print("  [red]Invalid hexadecimal number[/red]")
        
        elif sel == 5:  # Oct to Dec
            octal = ask("Enter octal number (without 0o)")
            try:
                decimal = int(octal, 8)
                console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
                console.print(f"  Octal: [yellow]{octal}[/yellow]")
                console.print(f"  Decimal: [yellow]{decimal}[/yellow]")
            except ValueError:
                console.print("  [red]Invalid octal number[/red]")
        
        elif sel == 6:  # Custom
            num = ask("Enter number")
            from_base = int(ask("From base (2-36)", "10"))
            to_base = int(ask("To base (2-36)", "10"))
            
            try:
                decimal = int(num, from_base)
                
                if to_base == 10:
                    result = str(decimal)
                elif to_base == 2:
                    result = bin(decimal)[2:]
                elif to_base == 8:
                    result = oct(decimal)[2:]
                elif to_base == 16:
                    result = hex(decimal)[2:].upper()
                else:
                    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    result = ""
                    while decimal > 0:
                        result = digits[decimal % to_base] + result
                        decimal //= to_base
                
                console.print(f"\n  [bold cyan]Conversion:[/bold cyan]")
                console.print(f"  Base {from_base}: [yellow]{num}[/yellow]")
                console.print(f"  Base {to_base}: [yellow]{result}[/yellow]")
            except ValueError:
                console.print(f"  [red]Invalid number for base {from_base}[/red]")
        
        pause()


def hash_generator():
    """Generate file/text hashes"""
    while True:
        header("Hash Generator", "Generate cryptographic hashes")
        
        opts = [
            "Hash Text (MD5/SHA)",
            "Hash File",
            "Compare Hashes",
            "Hash Password (bcrypt-style)",
        ]
        
        sel = numbered_menu("Hash Tools", opts)
        if sel == -1: return
        
        header("Hash Generator", opts[sel])
        
        if sel == 0:  # Hash Text
            text = ask("Enter text to hash")
            
            import hashlib
            
            md5 = hashlib.md5(text.encode()).hexdigest()
            sha1 = hashlib.sha1(text.encode()).hexdigest()
            sha256 = hashlib.sha256(text.encode()).hexdigest()
            sha512 = hashlib.sha512(text.encode()).hexdigest()
            
            console.print(f"\n  [bold cyan]Text Hashes:[/bold cyan]\n")
            console.print(f"  [bold]MD5:[/bold]")
            console.print(f"  [yellow]{md5}[/yellow]\n")
            console.print(f"  [bold]SHA-1:[/bold]")
            console.print(f"  [yellow]{sha1}[/yellow]\n")
            console.print(f"  [bold]SHA-256:[/bold]")
            console.print(f"  [yellow]{sha256}[/yellow]\n")
            console.print(f"  [bold]SHA-512:[/bold]")
            console.print(f"  [yellow]{sha512}[/yellow]")
        
        elif sel == 1:  # Hash File
            filepath = ask("Enter file path")
            
            if not os.path.exists(filepath):
                console.print(f"  [red]File not found: {filepath}[/red]")
                pause()
                continue
            
            import hashlib
            
            md5 = hashlib.md5()
            sha256 = hashlib.sha256()
            
            try:
                with open(filepath, 'rb') as f:
                    chunk = f.read(8192)
                    while chunk:
                        md5.update(chunk)
                        sha256.update(chunk)
                        chunk = f.read(8192)
                
                console.print(f"\n  [bold cyan]File Hashes:[/bold cyan]")
                console.print(f"  File: [dim]{filepath}[/dim]\n")
                console.print(f"  [bold]MD5:[/bold]")
                console.print(f"  [yellow]{md5.hexdigest()}[/yellow]\n")
                console.print(f"  [bold]SHA-256:[/bold]")
                console.print(f"  [yellow]{sha256.hexdigest()}[/yellow]")
            except Exception as e:
                console.print(f"  [red]Error reading file: {e}[/red]")
        
        elif sel == 2:  # Compare
            hash1 = ask("Enter first hash")
            hash2 = ask("Enter second hash")
            
            if hash1.lower() == hash2.lower():
                console.print(f"\n  [bold green]✓ Hashes MATCH[/bold green]")
            else:
                console.print(f"\n  [bold red]✗ Hashes DO NOT match[/bold red]")
        
        elif sel == 3:  # Password Hash
            password = ask("Enter password to hash")
            
            import hashlib
            salt = os.urandom(32)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            
            console.print(f"\n  [bold cyan]Password Hash (PBKDF2):[/bold cyan]\n")
            console.print(f"  [bold]Salt:[/bold]")
            console.print(f"  [dim]{salt.hex()}[/dim]\n")
            console.print(f"  [bold]Hash:[/bold]")
            console.print(f"  [yellow]{key.hex()}[/yellow]\n")
            console.print(f"  [dim]Note: Always use a proper password hashing library in production[/dim]")
        
        pause()


def regex_tester():
    """Test regular expressions"""
    while True:
        header("RegEx Tester", "Test regular expressions")
        
        pattern = ask("Enter regex pattern")
        test_string = ask("Enter test string (or type 'PASTE')")
        
        if test_string.upper() == "PASTE":
            console.print("  [dim]Paste text, CTRL+Z then ENTER:[/dim]")
            lines = []
            try:
                while True:
                    lines.append(input())
            except EOFError:
                test_string = "\n".join(lines)
        
        import re
        
        try:
            regex = re.compile(pattern)
            matches = regex.findall(test_string)
            
            console.print(f"\n  [bold cyan]Regex Test Results:[/bold cyan]\n")
            console.print(f"  Pattern: [yellow]{pattern}[/yellow]")
            console.print(f"  Matches found: [cyan]{len(matches)}[/cyan]\n")
            
            if matches:
                console.print(f"  [bold]Matches:[/bold]")
                for i, match in enumerate(matches[:20], 1):  # Show first 20
                    console.print(f"  {i}. [green]{match}[/green]")
                
                if len(matches) > 20:
                    console.print(f"  [dim]...and {len(matches) - 20} more[/dim]")
            else:
                console.print(f"  [yellow]No matches found[/yellow]")
            
            if regex.match(test_string):
                console.print(f"\n  [green]✓ match() - Pattern matches from start[/green]")
            else:
                console.print(f"\n  [red]✗ match() - Pattern does not match from start[/red]")
            
            if regex.search(test_string):
                console.print(f"  [green]✓ search() - Pattern found in string[/green]")
            else:
                console.print(f"  [red]✗ search() - Pattern not found[/red]")
            
        except re.error as e:
            console.print(f"\n  [red]Invalid regex pattern: {e}[/red]")
        
        pause()
        break








def git_helper():
    """Quick Git operations"""
    while True:
        header("Git Helper", "Quick Git operations")
        
        opts = [
            "Git Status",
            "View Recent Commits",
            "Quick Commit & Push",
            "Create Branch",
            "Switch Branch",
            "View Diff",
            "Undo Last Commit",
            "Stash Changes",
        ]
        
        sel = numbered_menu("Git Operations", opts)
        if sel == -1: return
        
        header("Git Helper", opts[sel])
        
        if sel == 0:  # Status
            result = subprocess.run(["git", "status"], capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout)
            if result.returncode != 0:
                console.print(f"[red]{result.stderr}[/red]")
        
        elif sel == 1:  # Recent commits
            count = int(ask("How many commits", "10"))
            result = subprocess.run(["git", "log", f"-{count}", "--oneline", "--decorate"], 
                                  capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout)
        
        elif sel == 2:  # Quick commit & push
            message = ask("Commit message")
            
            subprocess.run(["git", "add", "."], cwd=os.getcwd())
            console.print("  [yellow]Staged all changes[/yellow]")
            
            result = subprocess.run(["git", "commit", "-m", message], 
                                  capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout)
            
            if confirm("Push to remote?"):
                result = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=os.getcwd())
                console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
                if result.returncode == 0:
                    console.print("  [green]✓ Pushed successfully[/green]")
        
        elif sel == 3:  # Create branch
            branch_name = ask("New branch name")
            result = subprocess.run(["git", "checkout", "-b", branch_name], 
                                  capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 4:  # Switch branch
            result = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout)
            branch = ask("Branch name to switch to")
            result = subprocess.run(["git", "checkout", branch], 
                                  capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 5:  # View diff
            result = subprocess.run(["git", "diff"], capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout if result.stdout else "[dim]No changes[/dim]")
        
        elif sel == 6:  # Undo last commit
            if confirm("Undo last commit (keep changes)?"):
                result = subprocess.run(["git", "reset", "HEAD~1"], 
                                      capture_output=True, text=True, cwd=os.getcwd())
                console.print("  [green]✓ Last commit undone[/green]")
        
        elif sel == 7:  # Stash
            result = subprocess.run(["git", "stash"], capture_output=True, text=True, cwd=os.getcwd())
            console.print(result.stdout)
            console.print("  [green]✓ Changes stashed[/green]")
        
        pause()


def api_tester():
    """HTTP API testing tool"""
    while True:
        header("API Tester", "Test HTTP endpoints")
        
        url = ask("Enter API endpoint URL")
        
        opts = [
            "GET Request",
            "POST Request (JSON)",
            "PUT Request",
            "DELETE Request",
            "Custom Headers",
        ]
        
        sel = numbered_menu("HTTP Method", opts)
        if sel == -1: return
        
        headers = {"User-Agent": "DevTools-APITester"}
        
        if sel == 4:  # Custom headers
            console.print("  [dim]Enter headers (key:value), blank to finish[/dim]")
            while True:
                header_input = ask("Header (key:value)", "")
                if not header_input:
                    break
                try:
                    key, value = header_input.split(":", 1)
                    headers[key.strip()] = value.strip()
                except:
                    console.print("  [red]Invalid format[/red]")
            sel = numbered_menu("HTTP Method", ["GET", "POST", "PUT", "DELETE"])
        
        body = None
        if sel in [1, 2]:  # POST or PUT
            body_input = ask("JSON body (or type 'PASTE')")
            if body_input.upper() == "PASTE":
                console.print("  [dim]Paste JSON, CTRL+Z then ENTER:[/dim]")
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    body = "\n".join(lines)
            else:
                body = body_input
        
        console.print(f"\n  [yellow]Sending request...[/yellow]")
        
        try:
            import urllib.request
            
            if body:
                body = body.encode('utf-8')
                headers['Content-Type'] = 'application/json'
            
            methods = ["GET", "POST", "PUT", "DELETE"]
            method = methods[sel] if sel < 4 else methods[sel]
            
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=30) as response:
                elapsed = time.time() - start_time
                status = response.status
                response_body = response.read().decode('utf-8')
                
                console.print(f"\n  [bold cyan]Response:[/bold cyan]")
                console.print(f"  Status: [{'green' if status < 400 else 'red'}]{status}[/{'green' if status < 400 else 'red'}]")
                console.print(f"  Time: [yellow]{elapsed:.3f}s[/yellow]")
                console.print(f"\n  [bold]Body:[/bold]")
                
                try:
                    import json
                    parsed = json.loads(response_body)
                    formatted = json.dumps(parsed, indent=2)
                    console.print(formatted)
                except:
                    console.print(response_body)
                    
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        
        pause()
        break


def jwt_decoder():
    """Decode JWT tokens"""
    while True:
        header("JWT Decoder", "Decode JSON Web Tokens")
        
        token = ask("Enter JWT token")
        
        try:
            import base64
            import json
            
            parts = token.split('.')
            
            if len(parts) != 3:
                console.print("  [red]Invalid JWT format (should have 3 parts)[/red]")
                pause()
                continue
            
            header_data = parts[0]
            header_data += '=' * (4 - len(header_data) % 4)
            header_decoded = base64.urlsafe_b64decode(header_data).decode('utf-8')
            
            payload_data = parts[1]
            payload_data += '=' * (4 - len(payload_data) % 4)
            payload_decoded = base64.urlsafe_b64decode(payload_data).decode('utf-8')
            
            console.print(f"\n  [bold cyan]JWT Decoded:[/bold cyan]\n")
            
            console.print(f"  [bold yellow]Header:[/bold yellow]")
            header_json = json.loads(header_decoded)
            console.print(json.dumps(header_json, indent=2))
            
            console.print(f"\n  [bold yellow]Payload:[/bold yellow]")
            payload_json = json.loads(payload_decoded)
            console.print(json.dumps(payload_json, indent=2))
            
            if 'exp' in payload_json:
                import datetime
                exp_timestamp = payload_json['exp']
                exp_date = datetime.datetime.fromtimestamp(exp_timestamp)
                now = datetime.datetime.now()
                
                console.print(f"\n  [bold]Expiration:[/bold]")
                console.print(f"  {exp_date}")
                if now > exp_date:
                    console.print(f"  [red]✗ Token Expired[/red]")
                else:
                    console.print(f"  [green]✓ Token Valid[/green]")
            
            console.print(f"\n  [bold yellow]Signature:[/bold yellow]")
            console.print(f"  {parts[2][:50]}{'...' if len(parts[2]) > 50 else ''}")
            
        except Exception as e:
            console.print(f"  [red]Error decoding JWT: {e}[/red]")
        
        pause()
        break


def sql_formatter():
    """Format SQL queries"""
    while True:
        header("SQL Formatter", "Format and beautify SQL")
        
        sql = ask("Enter SQL query (or type 'PASTE')")
        
        if sql.upper() == "PASTE":
            console.print("  [dim]Paste SQL, CTRL+Z then ENTER:[/dim]")
            lines = []
            try:
                while True:
                    lines.append(input())
            except EOFError:
                sql = "\n".join(lines)
        
        sql = sql.strip()
        
        keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER', 
                   'ON', 'AND', 'OR', 'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET',
                   'INSERT INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'CREATE', 'TABLE',
                   'ALTER', 'DROP', 'AS', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN']
        
        formatted = sql
        for keyword in keywords:
            import re
            formatted = re.sub(f'\\b{keyword}\\b', keyword, formatted, flags=re.IGNORECASE)
        
        formatted = formatted.replace(' FROM ', '\nFROM ')
        formatted = formatted.replace(' WHERE ', '\nWHERE ')
        formatted = formatted.replace(' JOIN ', '\nJOIN ')
        formatted = formatted.replace(' LEFT JOIN ', '\nLEFT JOIN ')
        formatted = formatted.replace(' INNER JOIN ', '\nINNER JOIN ')
        formatted = formatted.replace(' ORDER BY ', '\nORDER BY ')
        formatted = formatted.replace(' GROUP BY ', '\nGROUP BY ')
        formatted = formatted.replace(' AND ', '\n  AND ')
        formatted = formatted.replace(' OR ', '\n  OR ')
        
        console.print(f"\n  [bold cyan]Formatted SQL:[/bold cyan]\n")
        console.print(formatted)
        
        param_count = formatted.count('?') + formatted.count('$')
        if param_count > 0:
            console.print(f"\n  [dim]Parameters: {param_count}[/dim]")
        
        pause()
        break


def docker_helper():
    """Quick Docker operations"""
    while True:
        header("Docker Helper", "Quick container operations")
        
        opts = [
            "List Running Containers",
            "List All Containers",
            "Stop Container",
            "Remove Container",
            "View Container Logs",
            "Container Stats",
            "Pull Image",
            "List Images",
        ]
        
        sel = numbered_menu("Docker Operations", opts)
        if sel == -1: return
        
        header("Docker Helper", opts[sel])
        
        if sel == 0:  # Running containers
            result = subprocess.run(["docker", "ps"], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 1:  # All containers
            result = subprocess.run(["docker", "ps", "-a"], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 2:  # Stop container
            container_id = ask("Container ID or name")
            result = subprocess.run(["docker", "stop", container_id], capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"  [green]✓ Stopped {container_id}[/green]")
            else:
                console.print(f"[red]{result.stderr}[/red]")
        
        elif sel == 3:  # Remove container
            container_id = ask("Container ID or name")
            result = subprocess.run(["docker", "rm", container_id], capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"  [green]✓ Removed {container_id}[/green]")
            else:
                console.print(f"[red]{result.stderr}[/red]")
        
        elif sel == 4:  # Logs
            container_id = ask("Container ID or name")
            lines = ask("Number of lines", "50")
            result = subprocess.run(["docker", "logs", "--tail", lines, container_id], 
                                  capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 5:  # Stats
            result = subprocess.run(["docker", "stats", "--no-stream"], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 6:  # Pull image
            image = ask("Image name (e.g., nginx:latest)")
            console.print(f"  [yellow]Pulling {image}...[/yellow]")
            result = subprocess.run(["docker", "pull", image], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        elif sel == 7:  # List images
            result = subprocess.run(["docker", "images"], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"[red]{result.stderr}[/red]")
        
        pause()


def port_manager():
    """Check and kill processes on ports"""
    while True:
        header("Port Manager", "Manage processes on ports")
        
        opts = [
            "Check Port",
            "Kill Process on Port",
            "List All Listening Ports",
            "Find Process by PID",
        ]
        
        sel = numbered_menu("Port Operations", opts)
        if sel == -1: return
        
        header("Port Manager", opts[sel])
        
        if sel == 0:  # Check port
            port = ask("Port number")
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            
            found = False
            for line in result.stdout.split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    console.print(line)
                    found = True
            
            if not found:
                console.print(f"  [yellow]Port {port} is free[/yellow]")
        
        elif sel == 1:  # Kill process on port
            port = ask("Port number")
            
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            
            pid = None
            for line in result.stdout.split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) > 4:
                        pid = parts[-1]
                        console.print(f"  Found process: PID {pid}")
                        break
            
            if pid:
                if confirm(f"Kill process {pid}?"):
                    result = subprocess.run(["taskkill", "/F", "/PID", pid], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        console.print(f"  [green]✓ Killed process {pid}[/green]")
                    else:
                        console.print(f"[red]{result.stderr}[/red]")
            else:
                console.print(f"  [yellow]No process found on port {port}[/yellow]")
        
        elif sel == 2:  # List all ports
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            
            console.print("\n  [bold cyan]Listening Ports:[/bold cyan]\n")
            for line in result.stdout.split('\n'):
                if "LISTENING" in line:
                    console.print(f"  {line}")
        
        elif sel == 3:  # Find process
            pid = ask("Process ID (PID)")
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/V"], 
                                  capture_output=True, text=True)
            console.print(result.stdout)
        
        pause()


def code_minifier():
    """Minify code (JS/CSS/JSON)"""
    while True:
        header("Code Minifier", "Minify JavaScript, CSS, JSON")
        
        opts = [
            "Minify JSON",
            "Minify CSS (Basic)",
            "Minify JavaScript (Basic)",
            "Remove Comments from Code",
        ]
        
        sel = numbered_menu("Minify", opts)
        if sel == -1: return
        
        header("Code Minifier", opts[sel])
        
        code = ask("Enter code (or type 'PASTE')")
        
        if code.upper() == "PASTE":
            console.print("  [dim]Paste code, CTRL+Z then ENTER:[/dim]")
            lines = []
            try:
                while True:
                    lines.append(input())
            except EOFError:
                code = "\n".join(lines)
        
        if sel == 0:  # JSON
            try:
                import json
                obj = json.loads(code)
                minified = json.dumps(obj, separators=(',', ':'))
                
                console.print(f"\n  [bold cyan]Minified JSON:[/bold cyan]")
                console.print(minified)
                console.print(f"\n  [dim]Original: {len(code)} chars → Minified: {len(minified)} chars ({(1-len(minified)/len(code))*100:.1f}% reduction)[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        
        elif sel == 1:  # CSS
            minified = code.replace('\n', '').replace('\r', '')
            minified = ' '.join(minified.split())  # Remove extra whitespace
            minified = minified.replace(': ', ':').replace('; ', ';')
            minified = minified.replace('{ ', '{').replace(' }', '}')
            
            console.print(f"\n  [bold cyan]Minified CSS:[/bold cyan]")
            console.print(minified)
            console.print(f"\n  [dim]Original: {len(code)} chars → Minified: {len(minified)} chars ({(1-len(minified)/len(code))*100:.1f}% reduction)[/dim]")
        
        elif sel == 2:  # JS
            minified = code.replace('\n', ' ').replace('\r', '')
            minified = ' '.join(minified.split())
            
            console.print(f"\n  [bold cyan]Minified JavaScript:[/bold cyan]")
            console.print(minified)
            console.print(f"\n  [dim]Original: {len(code)} chars → Minified: {len(minified)} chars ({(1-len(minified)/len(code))*100:.1f}% reduction)[/dim]")
            console.print(f"\n  [yellow]Note: For production, use a proper minifier like UglifyJS or Terser[/yellow]")
        
        elif sel == 3:  # Remove comments
            import re
            no_comments = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
            no_comments = re.sub(r'/\*.*?\*/', '', no_comments, flags=re.DOTALL)
            
            console.print(f"\n  [bold cyan]Code without comments:[/bold cyan]")
            console.print(no_comments)
        
        pause()
        break


def string_escaper():
    """Escape/unescape strings for different languages"""
    while True:
        header("String Escaper", "Escape for different languages")
        
        text = ask("Enter string to escape/unescape")
        
        opts = [
            "Escape for JavaScript/JSON",
            "Escape for Python",
            "Escape for SQL",
            "Escape for HTML",
            "Escape for URL",
            "Unescape JavaScript/JSON",
            "Unescape Python",
            "Unescape URL",
        ]
        
        sel = numbered_menu("Escape Type", opts)
        if sel == -1: return
        
        header("String Escaper", opts[sel])
        
        if sel == 0:  # JS/JSON escape
            import json
            result = json.dumps(text)[1:-1]  # Remove quotes
            console.print(f"\n  [bold cyan]Escaped:[/bold cyan]")
            console.print(f"  {result}")
        
        elif sel == 1:  # Python escape
            result = repr(text)[1:-1]
            console.print(f"\n  [bold cyan]Escaped:[/bold cyan]")
            console.print(f"  {result}")
        
        elif sel == 2:  # SQL escape
            result = text.replace("'", "''")
            console.print(f"\n  [bold cyan]SQL Escaped:[/bold cyan]")
            console.print(f"  {result}")
            console.print(f"\n  [dim]For parameterized queries: use ? or $1 placeholders[/dim]")
        
        elif sel == 3:  # HTML escape
            result = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            result = result.replace('"', '&quot;').replace("'", '&#39;')
            console.print(f"\n  [bold cyan]HTML Escaped:[/bold cyan]")
            console.print(f"  {result}")
        
        elif sel == 4:  # URL escape
            import urllib.parse
            result = urllib.parse.quote(text)
            console.print(f"\n  [bold cyan]URL Encoded:[/bold cyan]")
            console.print(f"  {result}")
        
        elif sel == 5:  # Unescape JS/JSON
            try:
                import json
                result = json.loads(f'"{text}"')
                console.print(f"\n  [bold cyan]Unescaped:[/bold cyan]")
                console.print(f"  {result}")
            except:
                console.print(f"  [red]Invalid escaped string[/red]")
        
        elif sel == 6:  # Unescape Python
            try:
                result = text.encode().decode('unicode_escape')
                console.print(f"\n  [bold cyan]Unescaped:[/bold cyan]")
                console.print(f"  {result}")
            except:
                console.print(f"  [red]Invalid escaped string[/red]")
        
        elif sel == 7:  # Unescape URL
            import urllib.parse
            result = urllib.parse.unquote(text)
            console.print(f"\n  [bold cyan]URL Decoded:[/bold cyan]")
            console.print(f"  {result}")
        
        pause()


def env_manager():
    """Environment variable manager"""
    while True:
        header("Environment Variable Manager", "Manage .env files")
        
        opts = [
            "View Current Env Vars",
            "Create .env File",
            "Add Variable to .env",
            "Load .env File",
            "Generate .env Template",
        ]
        
        sel = numbered_menu("Env Operations", opts)
        if sel == -1: return
        
        header("Env Manager", opts[sel])
        
        if sel == 0:  # View current
            console.print("\n  [bold cyan]Current Environment Variables:[/bold cyan]\n")
            for key, value in sorted(os.environ.items())[:20]:  # Show first 20
                console.print(f"  [yellow]{key}[/yellow] = [dim]{value[:50]}{'...' if len(value) > 50 else ''}[/dim]")
            console.print(f"\n  [dim]Showing 20 of {len(os.environ)} variables[/dim]")
        
        elif sel == 1:  # Create .env
            env_path = ask(".env file path", ".env")
            
            console.print("\n  [dim]Enter variables (KEY=VALUE), blank to finish:[/dim]")
            vars_list = []
            while True:
                var = ask("Variable", "")
                if not var:
                    break
                vars_list.append(var)
            
            with open(env_path, 'w') as f:
                for var in vars_list:
                    f.write(f"{var}\n")
            
            console.print(f"  [green]✓ Created {env_path}[/green]")
        
        elif sel == 2:  # Add variable
            env_path = ask(".env file path", ".env")
            
            if not os.path.exists(env_path):
                console.print(f"  [red]File not found: {env_path}[/red]")
                pause()
                continue
            
            key = ask("Variable name")
            value = ask("Variable value")
            
            with open(env_path, 'a') as f:
                f.write(f"\n{key}={value}\n")
            
            console.print(f"  [green]✓ Added {key} to {env_path}[/green]")
        
        elif sel == 3:  # Load .env
            env_path = ask(".env file path", ".env")
            
            if not os.path.exists(env_path):
                console.print(f"  [red]File not found: {env_path}[/red]")
                pause()
                continue
            
            with open(env_path, 'r') as f:
                lines = f.readlines()
            
            loaded = 0
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
                    loaded += 1
            
            console.print(f"  [green]✓ Loaded {loaded} variables from {env_path}[/green]")
        
        elif sel == 4:  # Generate template
            console.print("\n  [bold cyan]Common .env Template:[/bold cyan]\n")
            template = """# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp
DB_USER=postgres
DB_PASSWORD=

API_KEY=
API_SECRET=

APP_ENV=development
APP_PORT=3000
DEBUG=true

JWT_SECRET=
JWT_EXPIRES_IN=24h

REDIS_HOST=localhost
REDIS_PORT=6379
"""
            console.print(template)
            
            if confirm("Save this template to .env.example?"):
                with open(".env.example", 'w') as f:
                    f.write(template)
                console.print("  [green]✓ Saved to .env.example[/green]")
        
        pause()


def timestamp_converter():
    """Convert between timestamp formats"""
    while True:
        header("Timestamp Converter", "Unix time, ISO, human-readable")
        
        opts = [
            "Current Timestamp (All Formats)",
            "Unix Timestamp to Date",
            "Date to Unix Timestamp",
            "ISO 8601 to Human Readable",
            "Timestamp Math (Add/Subtract)",
        ]
        
        sel = numbered_menu("Timestamp Operations", opts)
        if sel == -1: return
        
        header("Timestamp Converter", opts[sel])
        
        import datetime
        
        if sel == 0:  # Current timestamp
            now = datetime.datetime.now()
            utc_now = datetime.datetime.utcnow()
            
            console.print(f"\n  [bold cyan]Current Timestamps:[/bold cyan]\n")
            console.print(f"  [bold]Unix Timestamp:[/bold]")
            console.print(f"  {int(now.timestamp())}")
            console.print(f"\n  [bold]Unix Timestamp (milliseconds):[/bold]")
            console.print(f"  {int(now.timestamp() * 1000)}")
            console.print(f"\n  [bold]ISO 8601:[/bold]")
            console.print(f"  {now.isoformat()}")
            console.print(f"\n  [bold]RFC 2822:[/bold]")
            console.print(f"  {now.strftime('%a, %d %b %Y %H:%M:%S %z')}")
            console.print(f"\n  [bold]Human Readable:[/bold]")
            console.print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
            console.print(f"\n  [bold]UTC:[/bold]")
            console.print(f"  {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        elif sel == 1:  # Unix to date
            timestamp = ask("Unix timestamp (seconds or milliseconds)")
            
            try:
                ts = int(timestamp)
                if ts > 10000000000:
                    ts = ts / 1000
                
                dt = datetime.datetime.fromtimestamp(ts)
                
                console.print(f"\n  [bold cyan]Converted:[/bold cyan]")
                console.print(f"  {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                console.print(f"  {dt.strftime('%A, %B %d, %Y at %I:%M:%S %p')}")
                console.print(f"\n  [dim]ISO 8601: {dt.isoformat()}[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        
        elif sel == 2:  # Date to Unix
            date_str = ask("Date (YYYY-MM-DD HH:MM:SS)")
            
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                unix_ts = int(dt.timestamp())
                
                console.print(f"\n  [bold cyan]Unix Timestamp:[/bold cyan]")
                console.print(f"  {unix_ts}")
                console.print(f"  {unix_ts * 1000} [dim](milliseconds)[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        
        elif sel == 3:  # ISO to human
            iso_str = ask("ISO 8601 timestamp")
            
            try:
                dt = datetime.datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
                
                console.print(f"\n  [bold cyan]Human Readable:[/bold cyan]")
                console.print(f"  {dt.strftime('%A, %B %d, %Y')}")
                console.print(f"  {dt.strftime('%I:%M:%S %p')}")
                console.print(f"\n  [dim]Unix: {int(dt.timestamp())}[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        
        elif sel == 4:  # Timestamp math
            timestamp = int(ask("Starting Unix timestamp"))
            operation = numbered_menu("Operation", ["Add time", "Subtract time"])
            
            if operation == -1:
                continue
            
            days = int(ask("Days", "0"))
            hours = int(ask("Hours", "0"))
            minutes = int(ask("Minutes", "0"))
            
            dt = datetime.datetime.fromtimestamp(timestamp)
            delta = datetime.timedelta(days=days, hours=hours, minutes=minutes)
            
            if operation == 0:
                result_dt = dt + delta
            else:
                result_dt = dt - delta
            
            console.print(f"\n  [bold cyan]Result:[/bold cyan]")
            console.print(f"  Unix: {int(result_dt.timestamp())}")
            console.print(f"  Date: {result_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        pause()





def shodan_search():
    while True:
        header("Shodan Search Helper", "Build Shodan dork queries")
        console.print("  [dim]Shodan is a search engine for IoT, servers, and cameras.[/dim]\n")
        
        opts = [
            "IP lookup (requires Shodan API key)",
            "Build custom Shodan dork",
            "Vulnerable device finder",
            "Default credential scanner",
        ]
        sel = numbered_menu("Shodan", opts)
        if sel == -1: return
        header("Shodan", opts[sel])

        if sel == 0:
            ip = ask("IP address")
            key = ask("Shodan API key (from shodan.io)")
            if not key:
                console.print("  [dim]Get free key at https://www.shodan.io[/dim]"); pause(); continue
            data = http_json(f"https://api.shodan.io/shodan/host/{ip}?key={key}", timeout=10)
            if data and data.get("ip_str"):
                t = Table(box=box.ROUNDED, show_header=False)
                t.add_column("k", style="cyan", width=18)
                t.add_column("v", style="white", width=50)
                t.add_row("IP", data.get("ip_str",""))
                t.add_row("Organization", data.get("org",""))
                t.add_row("Port Count", str(data.get("port_count","")))
                t.add_row("Country", data.get("country_name",""))
                for port_data in data.get("data",[])[:5]:
                    t.add_row(f"Port {port_data.get('port','')}",
                              port_data.get("product","")[:45])
                console.print(t)
            else:
                console.print("  [red]Not found or API error.[/red]")

        elif sel == 1:
            console.print("  [bold]Shodan Dork Examples:[/bold]\n")
            dorks = [
                ("Webcams", "webcam inurl:view.shtml"),
                ("Default login", 'http.title:"admin" port:80'),
                ("Raspberry Pi", 'product:"Raspberry Pi"'),
                ("Routers", 'product:"Ubiquiti EdgeRouter"'),
                ("Printers", 'port:9100 product:printer'),
                ("Databases", 'product:MongoDB'),
                ("CCTV", 'product:"CCTV" port:8080'),
                ("ICS/SCADA", 'product:"Siemens"'),
            ]
            for name, dork in dorks:
                console.print(f"  {name:<16} [cyan]{dork}[/cyan]")
            custom = ask("\nCreate custom dork")
            if custom:
                url = f"https://www.shodan.io/search?query={urllib.parse.quote(custom)}"
                subprocess.Popen(["cmd","/c","start","",url])

        elif sel == 2:
            vulndevs = [
                'product:"DJI Phantom"',
                'product:"Hikvision"',
                'port:445 product:Windows',
                'http.title:"NETGEAR"',
                'product:"Fortinet"',
            ]
            console.print("  [yellow]Common vulnerable devices:[/yellow]\n")
            for v in vulndevs:
                console.print(f"    {v}")
            
        elif sel == 3:
            console.print("  [bold]Default credentials (common):[/bold]\n")
            defaults = [
                ("admin:admin", "Many routers, cameras"),
                ("root:root", "Linux systems"),
                ("admin:password", "Various devices"),
                ("root:toor", "Old Linux"),
                ("default:default", "Some IoT"),
            ]
            for cred, desc in defaults:
                console.print(f"  [yellow]{cred:<20}[/yellow] {desc}")

        pause()


def ip_reputation():
    while True:
        header("IP Reputation Checker", "Spam, malware, blacklist status")
        ip = ask("IP address to check (B=back)").strip()
        if ip.lower() in ("b",""): return

        console.print(f"\n  [yellow]Checking reputation of {ip}...[/yellow]\n")

        sources = {}

        console.print("  [dim]Checking AbuseIPDB...[/dim]")
        abuse = http_json(f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90", timeout=8)
        if abuse and abuse.get("data"):
            d = abuse["data"]
            sources["AbuseIPDB"] = {
                "score": d.get("abuseConfidenceScore",0),
                "reports": d.get("totalReports",0)
            }

        console.print("  [dim]Checking IPQualityScore...[/dim]")
        iquals = http_json(f"https://ipqualityscore.com/api/json/ip/reputation?ip={ip}&strictness=0", timeout=8)
        if iquals and iquals.get("fraud_score"):
            sources["IQualityScore"] = {"fraud_score": iquals["fraud_score"]}

        t = Table(box=box.ROUNDED, show_header=False)
        t.add_column("Source", style="cyan", width=20)
        t.add_column("Result", style="white", width=50)
        
        t.add_row("IP", ip)
        for source, data in sources.items():
            if "score" in data:
                score = data["score"]
                col = "red" if score>50 else "yellow" if score>20 else "green"
                t.add_row(source, f"[{col}]Abuse Score: {score}[/{col}]")
            elif "fraud_score" in data:
                score = data["fraud_score"]
                col = "red" if score>75 else "yellow" if score>40 else "green"
                t.add_row(source, f"[{col}]Fraud Score: {score}[/{col}]")

        if not sources:
            console.print("  [dim]No reputation data found (likely clean).[/dim]")
        else:
            console.print(t)

        pause()


def wayback_machine():
    while True:
        header("Wayback Machine Analyzer", "Historical snapshots of websites")
        url = ask("Domain or URL (B=back)").strip()
        if url.lower() in ("b",""): return

        url = url.replace("https://","").replace("http://","").split("/")[0]
        console.print(f"\n  [yellow]Searching Wayback Machine for {url}...[/yellow]\n")

        data = http_json(f"https://archive.org/wayback/available?url={url}", timeout=10)
        if data and data.get("archived_snapshots"):
            snaps = data["archived_snapshots"]
            if snaps.get("closest"):
                c = snaps["closest"]
                console.print(f"  [bold]Latest snapshot:[/bold]")
                console.print(f"  Date: [cyan]{c['timestamp']}[/cyan]")
                console.print(f"  Status: [dim]{c['status']}[/dim]")
                console.print(f"  URL: [dim]{c['url']}[/dim]")
                
                if confirm("Open in browser?"):
                    subprocess.Popen(["cmd","/c","start","",c['url']])

            cal_url = f"https://archive.org/wayback/available?url={url}&output=json"
            console.print(f"\n  [bold]Browse:[/bold] https://web.archive.org/web/*/{url}/")
        else:
            console.print("  [dim]No snapshots found.[/dim]")

        pause()


def api_key_detector():
    while True:
        header("API Key Detector", "Find exposed API keys in websites")
        url = ask("Website URL (B=back)").strip()
        if url.lower() in ("b",""): return
        if not url.startswith("http"): url = "https://" + url

        console.print(f"\n  [yellow]Scanning {url} for API keys...[/yellow]\n")

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                html = r.read().decode("utf-8", errors="replace")
        except Exception as e:
            console.print(f"  [red]{e}[/red]"); pause(); continue

        patterns = {
            "[underscore](api|secret|key|token)": r'["\']?([a-zA-Z0-9_-]{20,60})["\']?\s*[:=]',
            "AWS Key": r"AKIA[0-9A-Z]{16}",
            "GitHub Token": r"ghp_[a-zA-Z0-9]{36}",
            "Slack Token": r"xoxb?-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24}",
            "Google API": r"AIza[0-9A-Za-z\-_]{35}",
            "Stripe Key": r"sk_live_[a-zA-Z0-9]{24}",
            "Firebase": r"AIDAI[a-zA-Z0-9_-]{35}",
        }

        found = {}
        for name, pattern in patterns.items():
            matches = re.findall(pattern, html)
            if matches:
                found[name] = len(matches)

        if found:
            console.print("  [bold red]⚠ Potential exposed keys found:[/bold red]\n")
            for key_type, count in found.items():
                console.print(f"  [red]{key_type}[/red]: {count} match(es)")
            console.print("\n  [yellow]! Report to the website admin immediately![/yellow]")
        else:
            console.print("  [green]No obvious exposed keys detected.[/green]")

        pause()



def scheduled_tasks_viewer():
    """View and manage Windows scheduled tasks"""
    while True:
        header("Scheduled Tasks", "View & manage Windows tasks")
        opts = ["List All Tasks", "View Task Details", "Disable a Task", "Enable a Task", "Delete a Task"]
        sel = numbered_menu("Scheduled Tasks", opts)
        if sel == -1: return
        header("Scheduled Tasks", opts[sel])
        if sel == 0:
            result = subprocess.run(["schtasks", "/query", "/fo", "TABLE", "/nh"], capture_output=True, text=True)
            lines = [l for l in result.stdout.split('\n') if l.strip()]
            for line in lines[:40]:
                console.print(f"  {line}")
            if len(lines) > 40:
                console.print(f"  [dim]... and {len(lines)-40} more[/dim]")
        elif sel == 1:
            name = ask("Task name")
            result = subprocess.run(["schtasks", "/query", "/tn", name, "/v", "/fo", "LIST"], capture_output=True, text=True)
            console.print(result.stdout if result.returncode == 0 else f"  [red]{result.stderr}[/red]")
        elif sel == 2:
            name = ask("Task name to disable")
            result = subprocess.run(["schtasks", "/change", "/tn", name, "/disable"], capture_output=True, text=True)
            console.print(f"  [green]✓ Disabled[/green]" if result.returncode == 0 else f"  [red]{result.stderr}[/red]")
        elif sel == 3:
            name = ask("Task name to enable")
            result = subprocess.run(["schtasks", "/change", "/tn", name, "/enable"], capture_output=True, text=True)
            console.print(f"  [green]✓ Enabled[/green]" if result.returncode == 0 else f"  [red]{result.stderr}[/red]")
        elif sel == 4:
            name = ask("Task name to delete")
            if confirm(f"Delete task '{name}'?"):
                result = subprocess.run(["schtasks", "/delete", "/tn", name, "/f"], capture_output=True, text=True)
                console.print(f"  [green]✓ Deleted[/green]" if result.returncode == 0 else f"  [red]{result.stderr}[/red]")
        pause()


def hosts_file_editor():
    """View and edit the Windows hosts file"""
    while True:
        header("Hosts File Editor", "Manage domain redirects")
        opts = ["View Hosts File", "Add Entry", "Remove Entry", "Block a Domain", "Unblock a Domain"]
        sel = numbered_menu("Hosts File", opts)
        if sel == -1: return
        header("Hosts File", opts[sel])
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        if sel == 0:
            try:
                with open(hosts_path, 'r') as f:
                    content = f.read()
                console.print(f"\n  [bold cyan]Hosts File:[/bold cyan]\n")
                for line in content.split('\n'):
                    if line.strip().startswith('#'):
                        console.print(f"  [dim]{line}[/dim]")
                    elif line.strip():
                        console.print(f"  [yellow]{line}[/yellow]")
            except PermissionError:
                console.print("  [red]Need admin privileges to read hosts file[/red]")
        elif sel == 1:
            ip = ask("IP address", "127.0.0.1")
            domain = ask("Domain name")
            try:
                with open(hosts_path, 'a') as f:
                    f.write(f"\n{ip}\t{domain}\n")
                console.print(f"  [green]✓ Added {ip} → {domain}[/green]")
            except PermissionError:
                console.print("  [red]Need admin privileges[/red]")
        elif sel == 2:
            domain = ask("Domain to remove")
            try:
                with open(hosts_path, 'r') as f:
                    lines = f.readlines()
                new_lines = [l for l in lines if domain not in l]
                with open(hosts_path, 'w') as f:
                    f.writelines(new_lines)
                console.print(f"  [green]✓ Removed entries for {domain}[/green]")
            except PermissionError:
                console.print("  [red]Need admin privileges[/red]")
        elif sel == 3:
            domain = ask("Domain to block")
            try:
                with open(hosts_path, 'a') as f:
                    f.write(f"\n127.0.0.1\t{domain}\n")
                console.print(f"  [green]✓ Blocked {domain}[/green]")
            except PermissionError:
                console.print("  [red]Need admin privileges[/red]")
        elif sel == 4:
            domain = ask("Domain to unblock")
            try:
                with open(hosts_path, 'r') as f:
                    lines = f.readlines()
                new_lines = [l for l in lines if domain not in l]
                with open(hosts_path, 'w') as f:
                    f.writelines(new_lines)
                console.print(f"  [green]✓ Unblocked {domain}[/green]")
            except PermissionError:
                console.print("  [red]Need admin privileges[/red]")
        pause()


def wifi_manager():
    """View saved WiFi passwords and networks"""
    while True:
        header("WiFi Manager", "View networks & saved passwords")
        opts = ["List Saved Networks", "Show WiFi Password", "Current Connection Info", "Disconnect WiFi", "Export All Passwords"]
        sel = numbered_menu("WiFi", opts)
        if sel == -1: return
        header("WiFi Manager", opts[sel])
        if sel == 0:
            result = subprocess.run(["netsh", "wlan", "show", "profiles"], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if "All User Profile" in line:
                    name = line.split(":")[-1].strip()
                    console.print(f"  [cyan]•[/cyan] {name}")
        elif sel == 1:
            network = ask("Network name")
            result = subprocess.run(["netsh", "wlan", "show", "profile", network, "key=clear"], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if "Key Content" in line:
                    password = line.split(":")[-1].strip()
                    console.print(f"\n  [bold]Network:[/bold] {network}")
                    console.print(f"  [bold]Password:[/bold] [yellow]{password}[/yellow]")
                    break
            else:
                console.print(f"  [red]No password found for '{network}'[/red]")
        elif sel == 2:
            result = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True)
            console.print(result.stdout)
        elif sel == 3:
            result = subprocess.run(["netsh", "wlan", "disconnect"], capture_output=True, text=True)
            console.print(f"  [green]✓ Disconnected[/green]" if result.returncode == 0 else f"  [red]{result.stderr}[/red]")
        elif sel == 4:
            result = subprocess.run(["netsh", "wlan", "show", "profiles"], capture_output=True, text=True)
            profiles = [l.split(":")[-1].strip() for l in result.stdout.split('\n') if "All User Profile" in l]
            console.print(f"\n  [bold cyan]All Saved WiFi Passwords:[/bold cyan]\n")
            for profile in profiles:
                r = subprocess.run(["netsh", "wlan", "show", "profile", profile, "key=clear"], capture_output=True, text=True)
                pw = ""
                for line in r.stdout.split('\n'):
                    if "Key Content" in line:
                        pw = line.split(":")[-1].strip()
                        break
                console.print(f"  [cyan]{profile:<30}[/cyan] [yellow]{pw or '[no password]'}[/yellow]")
        pause()


def installed_programs():
    """List and manage installed programs"""
    while True:
        header("Installed Programs", "View & uninstall software")
        opts = ["List All Programs", "Search Program", "Uninstall Program"]
        sel = numbered_menu("Programs", opts)
        if sel == -1: return
        header("Installed Programs", opts[sel])
        if sel == 0:
            result = subprocess.run(["wmic", "product", "get", "name,version"], capture_output=True, text=True)
            if result.returncode != 0:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName, DisplayVersion | Sort-Object DisplayName | Format-Table -AutoSize"],
                    capture_output=True, text=True
                )
            console.print(result.stdout)
        elif sel == 1:
            query = ask("Search term")
            result = subprocess.run(
                ["powershell", "-Command", f"Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Where-Object {{$_.DisplayName -like '*{query}*'}} | Select-Object DisplayName, DisplayVersion | Format-Table -AutoSize"],
                capture_output=True, text=True
            )
            console.print(result.stdout if result.stdout.strip() else f"  [dim]No programs matching '{query}'[/dim]")
        elif sel == 2:
            name = ask("Program name to uninstall")
            console.print(f"  [yellow]Looking for '{name}'...[/yellow]")
            result = subprocess.run(
                ["powershell", "-Command", f"Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Where-Object {{$_.DisplayName -like '*{name}*'}} | Select-Object DisplayName, UninstallString | Format-List"],
                capture_output=True, text=True
            )
            console.print(result.stdout)
            if confirm("Run uninstaller?"):
                for line in result.stdout.split('\n'):
                    if 'UninstallString' in line:
                        cmd = line.split(':', 1)[-1].strip()
                        os.system(cmd)
                        break
        pause()


def disk_space_analyzer():
    """Analyze disk space usage"""
    while True:
        header("Disk Space Analyzer", "Find what's eating your storage")
        opts = ["Drive Overview", "Largest Folders (User)", "Largest Files in Folder", "Temp Files Size", "Recycle Bin Size"]
        sel = numbered_menu("Disk Space", opts)
        if sel == -1: return
        header("Disk Space", opts[sel])
        if sel == 0:
            result = subprocess.run(
                ["powershell", "-Command", "Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='Used(GB)';E={[math]::Round($_.Used/1GB,2)}}, @{N='Free(GB)';E={[math]::Round($_.Free/1GB,2)}}, @{N='Total(GB)';E={[math]::Round(($_.Used+$_.Free)/1GB,2)}} | Format-Table -AutoSize"],
                capture_output=True, text=True
            )
            console.print(result.stdout)
        elif sel == 1:
            console.print("  [yellow]Scanning user profile folders...[/yellow]")
            user_path = os.path.expanduser("~")
            folders = []
            try:
                for item in os.listdir(user_path):
                    full = os.path.join(user_path, item)
                    if os.path.isdir(full):
                        try:
                            size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fns in os.walk(full) for f in fns)
                            folders.append((item, size))
                        except Exception:
                            pass
                folders.sort(key=lambda x: x[1], reverse=True)
                for name, size in folders[:15]:
                    if size > 1024*1024*1024:
                        sz = f"{size/1024/1024/1024:.2f} GB"
                    elif size > 1024*1024:
                        sz = f"{size/1024/1024:.1f} MB"
                    else:
                        sz = f"{size/1024:.0f} KB"
                    console.print(f"  [cyan]{name:<30}[/cyan] [yellow]{sz:>10}[/yellow]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 2:
            folder = ask("Folder path", os.path.expanduser("~"))
            console.print(f"  [yellow]Scanning...[/yellow]")
            files = []
            try:
                for dp, dn, fns in os.walk(folder):
                    for f in fns:
                        try:
                            fp = os.path.join(dp, f)
                            files.append((fp, os.path.getsize(fp)))
                        except Exception:
                            pass
                files.sort(key=lambda x: x[1], reverse=True)
                for path, size in files[:20]:
                    if size > 1024*1024*1024:
                        sz = f"{size/1024/1024/1024:.2f} GB"
                    elif size > 1024*1024:
                        sz = f"{size/1024/1024:.1f} MB"
                    else:
                        sz = f"{size/1024:.0f} KB"
                    console.print(f"  [yellow]{sz:>10}[/yellow]  [dim]{path}[/dim]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 3:
            temp_dirs = [os.environ.get('TEMP', ''), os.environ.get('TMP', ''), r'C:\Windows\Temp']
            total = 0
            for td in temp_dirs:
                if td and os.path.isdir(td):
                    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fns in os.walk(td) for f in fns if os.path.exists(os.path.join(dp, f)))
                    total += size
                    console.print(f"  [cyan]{td}[/cyan]: [yellow]{size/1024/1024:.1f} MB[/yellow]")
            console.print(f"\n  [bold]Total temp: {total/1024/1024:.1f} MB[/bold]")
            if confirm("Clean temp files?"):
                for td in temp_dirs:
                    if td and os.path.isdir(td):
                        for dp, dn, fns in os.walk(td):
                            for f in fns:
                                try: os.remove(os.path.join(dp, f))
                                except Exception:
                                    pass
                console.print(f"  [green]✓ Cleaned[/green]")
        elif sel == 4:
            result = subprocess.run(
                ["powershell", "-Command", "(New-Object -ComObject Shell.Application).NameSpace(0xA).Items() | Measure-Object -Property Size -Sum | Select-Object @{N='Count';E={$_.Count}}, @{N='Size(MB)';E={[math]::Round($_.Sum/1MB,2)}} | Format-List"],
                capture_output=True, text=True
            )
            console.print(result.stdout)
        pause()



def dns_optimizer():
    """Switch DNS servers for faster browsing"""
    while True:
        header("DNS Optimizer", "Switch to faster DNS servers")
        opts = [
            "View Current DNS",
            "Set Cloudflare DNS (1.1.1.1)",
            "Set Google DNS (8.8.8.8)",
            "Set Quad9 DNS (9.9.9.9)",
            "Set OpenDNS (208.67.222.222)",
            "Reset to Automatic (DHCP)",
            "Flush DNS Cache",
        ]
        sel = numbered_menu("DNS", opts)
        if sel == -1: return
        header("DNS Optimizer", opts[sel])
        if sel == 0:
            result = subprocess.run(["powershell", "-Command", "Get-DnsClientServerAddress -AddressFamily IPv4 | Format-Table InterfaceAlias, ServerAddresses -AutoSize"], capture_output=True, text=True)
            console.print(result.stdout)
        elif sel in (1, 2, 3, 4):
            dns_map = {
                1: ("1.1.1.1", "1.0.0.1"),
                2: ("8.8.8.8", "8.8.4.4"),
                3: ("9.9.9.9", "149.112.112.112"),
                4: ("208.67.222.222", "208.67.220.220"),
            }
            primary, secondary = dns_map[sel]
            result = subprocess.run(["powershell", "-Command", "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1 -ExpandProperty Name"], capture_output=True, text=True)
            adapter = result.stdout.strip()
            if adapter:
                subprocess.run(["netsh", "interface", "ip", "set", "dns", adapter, "static", primary], capture_output=True)
                subprocess.run(["netsh", "interface", "ip", "add", "dns", adapter, secondary, "index=2"], capture_output=True)
                console.print(f"  [green]✓ DNS set to {primary} / {secondary} on {adapter}[/green]")
            else:
                console.print("  [red]No active network adapter found[/red]")
        elif sel == 5:
            result = subprocess.run(["powershell", "-Command", "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1 -ExpandProperty Name"], capture_output=True, text=True)
            adapter = result.stdout.strip()
            subprocess.run(["netsh", "interface", "ip", "set", "dns", adapter, "dhcp"], capture_output=True)
            console.print(f"  [green]✓ DNS reset to automatic[/green]")
        elif sel == 6:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
            console.print("  [green]✓ DNS cache flushed[/green]")
        pause()


def ram_optimizer():
    """Free up RAM and optimize memory usage"""
    while True:
        header("RAM Optimizer", "Free up memory")
        opts = [
            "View RAM Usage",
            "Clear Standby Memory",
            "Kill High-RAM Processes",
            "Set Process Priority (Low)",
            "Disable Superfetch/Prefetch",
        ]
        sel = numbered_menu("RAM", opts)
        if sel == -1: return
        header("RAM Optimizer", opts[sel])
        if sel == 0:
            import psutil
            mem = psutil.virtual_memory()
            console.print(f"\n  [bold]Total:     [cyan]{mem.total/1024/1024/1024:.1f} GB[/cyan][/bold]")
            console.print(f"  [bold]Used:      [yellow]{mem.used/1024/1024/1024:.1f} GB ({mem.percent}%)[/yellow][/bold]")
            console.print(f"  [bold]Available: [green]{mem.available/1024/1024/1024:.1f} GB[/green][/bold]")
            console.print(f"\n  [bold cyan]Top RAM Consumers:[/bold cyan]\n")
            procs = []
            for p in psutil.process_iter(['name', 'memory_info']):
                try:
                    procs.append((p.info['name'], p.info['memory_info'].rss))
                except Exception:
                    pass
            procs.sort(key=lambda x: x[1], reverse=True)
            for name, mem_bytes in procs[:10]:
                console.print(f"  [yellow]{mem_bytes/1024/1024:>8.1f} MB[/yellow]  {name}")
        elif sel == 1:
            console.print("  [yellow]Clearing standby memory...[/yellow]")
            subprocess.run(["powershell", "-Command", "[System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers()"], capture_output=True)
            gc.collect()
            console.print("  [green]✓ Memory cleaned[/green]")
        elif sel == 2:
            import psutil
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    procs.append((p.info['pid'], p.info['name'], p.info['memory_info'].rss))
                except Exception:
                    pass
            procs.sort(key=lambda x: x[2], reverse=True)
            console.print(f"\n  [bold cyan]High RAM Processes:[/bold cyan]\n")
            for pid, name, mem_bytes in procs[:10]:
                console.print(f"  [yellow]{mem_bytes/1024/1024:>8.1f} MB[/yellow]  {name} (PID: {pid})")
            kill_pid = ask("Enter PID to kill (or blank to skip)", "")
            if kill_pid.isdigit():
                try:
                    psutil.Process(int(kill_pid)).kill()
                    console.print(f"  [green]✓ Killed PID {kill_pid}[/green]")
                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")
        elif sel == 3:
            pid = ask("Process PID")
            try:
                import psutil
                p = psutil.Process(int(pid))
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                console.print(f"  [green]✓ Set {p.name()} to below-normal priority[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 4:
            subprocess.run(["sc", "config", "SysMain", "start=", "disabled"], capture_output=True)
            subprocess.run(["sc", "stop", "SysMain"], capture_output=True)
            console.print("  [green]✓ Superfetch disabled[/green]")
        pause()


def windows_update_manager():
    """Manage Windows Update settings"""
    while True:
        header("Windows Update Manager", "Control update behavior")
        opts = [
            "Check for Updates",
            "View Update History",
            "Pause Updates (35 days)",
            "Resume Updates",
            "Clear Update Cache",
        ]
        sel = numbered_menu("Windows Update", opts)
        if sel == -1: return
        header("Update Manager", opts[sel])
        if sel == 0:
            console.print("  [yellow]Checking for updates...[/yellow]")
            result = subprocess.run(["powershell", "-Command", "Get-WindowsUpdate -MicrosoftUpdate 2>$null || Write-Output 'WindowsUpdate module not installed - use: Install-Module PSWindowsUpdate'"], capture_output=True, text=True)
            console.print(result.stdout)
        elif sel == 1:
            result = subprocess.run(["powershell", "-Command", "Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 20 | Format-Table HotFixID, Description, InstalledOn -AutoSize"], capture_output=True, text=True)
            console.print(result.stdout)
        elif sel == 2:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", 0, winreg.KEY_SET_VALUE)
                import datetime
                pause_date = (datetime.datetime.now() + datetime.timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
                winreg.SetValueEx(key, "PauseUpdatesExpiryTime", 0, winreg.REG_SZ, pause_date)
                winreg.CloseKey(key)
                console.print(f"  [green]✓ Updates paused for 35 days[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 3:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "PauseUpdatesExpiryTime")
                winreg.CloseKey(key)
                console.print("  [green]✓ Updates resumed[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 4:
            console.print("  [yellow]Clearing update cache...[/yellow]")
            subprocess.run(["net", "stop", "wuauserv"], capture_output=True)
            shutil.rmtree(r"C:\Windows\SoftwareDistribution\Download", ignore_errors=True)
            subprocess.run(["net", "start", "wuauserv"], capture_output=True)
            console.print("  [green]✓ Update cache cleared[/green]")
        pause()


def background_process_optimizer():
    """Disable unnecessary background processes"""
    while True:
        header("Background Process Optimizer", "Kill bloat silently")
        opts = [
            "List Background Processes",
            "Kill Common Bloatware",
            "Disable Background Apps (Registry)",
            "View Processes by CPU Usage",
        ]
        sel = numbered_menu("Background Optimizer", opts)
        if sel == -1: return
        header("Background Optimizer", opts[sel])
        if sel == 0:
            import psutil
            bg = [(p.info['name'], p.info['memory_info'].rss) for p in psutil.process_iter(['name', 'memory_info']) if p.info['name'] and p.info['memory_info']]
            bg.sort(key=lambda x: x[1], reverse=True)
            for name, mem in bg[:30]:
                console.print(f"  [cyan]{name:<35}[/cyan] [yellow]{mem/1024/1024:.1f} MB[/yellow]")
        elif sel == 1:
            bloat = ["OneDrive.exe", "YourPhone.exe", "SkypeApp.exe", "Cortana.exe", 
                     "GameBar.exe", "HxTsr.exe", "MicrosoftEdgeUpdate.exe"]
            import psutil
            killed = 0
            for p in psutil.process_iter(['name', 'pid']):
                if p.info['name'] in bloat:
                    try:
                        p.kill()
                        console.print(f"  [green]✓ Killed {p.info['name']}[/green]")
                        killed += 1
                    except Exception:
                        pass
            console.print(f"\n  [bold]Killed {killed} bloatware processes[/bold]")
        elif sel == 2:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "GlobalUserDisabled", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)
                console.print("  [green]✓ Background apps disabled[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 3:
            import psutil
            procs = [(p.info['name'], p.info['cpu_percent']) for p in psutil.process_iter(['name', 'cpu_percent']) if p.info['cpu_percent'] and p.info['cpu_percent'] > 0]
            procs.sort(key=lambda x: x[1], reverse=True)
            for name, cpu in procs[:20]:
                console.print(f"  [cyan]{name:<35}[/cyan] [yellow]{cpu:.1f}%[/yellow]")
        pause()


def notification_disabler():
    """Disable Windows notifications and tips"""
    while True:
        header("Notification Disabler", "Silence Windows nagging")
        opts = [
            "Disable All Notifications",
            "Disable Tips & Suggestions",
            "Disable Lock Screen Tips",
            "Enable Focus Assist (Priority Only)",
            "Re-enable All Notifications",
        ]
        sel = numbered_menu("Notifications", opts)
        if sel == -1: return
        header("Notifications", opts[sel])
        try:
            if sel == 0:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "ToastEnabled", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(key)
                console.print("  [green]✓ Notifications disabled[/green]")
            elif sel == 1:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "SoftLandingEnabled", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "SubscribedContent-338389Enabled", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(key)
                console.print("  [green]✓ Tips & suggestions disabled[/green]")
            elif sel == 2:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "RotatingLockScreenOverlayEnabled", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "SubscribedContent-338387Enabled", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(key)
                console.print("  [green]✓ Lock screen tips disabled[/green]")
            elif sel == 3:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(key)
                console.print("  [green]✓ Focus Assist enabled[/green]")
            elif sel == 4:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "ToastEnabled", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)
                console.print("  [green]✓ Notifications re-enabled[/green]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        pause()



def http_header_analyzer():
    """Analyze HTTP response headers from a URL"""
    while True:
        header("HTTP Header Analyzer", "Inspect server response headers")
        url = ask("Enter URL (including https://)")
        try:
            req = urllib.request.Request(url, method='HEAD', headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                console.print(f"\n  [bold cyan]HTTP {resp.status}[/bold cyan]\n")
                for key, val in resp.headers.items():
                    if key.lower() in ('server', 'x-powered-by', 'x-aspnet-version', 'x-frame-options',
                                       'content-security-policy', 'strict-transport-security',
                                       'x-xss-protection', 'x-content-type-options', 'set-cookie'):
                        console.print(f"  [yellow]{key}[/yellow]: {val}")
                    else:
                        console.print(f"  [dim]{key}[/dim]: {val}")
                console.print(f"\n  [bold]Security Headers Check:[/bold]")
                headers_lower = {k.lower(): v for k, v in resp.headers.items()}
                checks = [
                    ("strict-transport-security", "HSTS"),
                    ("x-frame-options", "Clickjack Protection"),
                    ("x-content-type-options", "MIME Sniffing Protection"),
                    ("content-security-policy", "CSP"),
                    ("x-xss-protection", "XSS Protection"),
                ]
                for hdr, desc in checks:
                    if hdr in headers_lower:
                        console.print(f"  [green]✓ {desc}[/green]")
                    else:
                        console.print(f"  [red]✗ {desc} missing[/red]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        pause()
        break


def technology_detector():
    """Detect technologies used by a website"""
    while True:
        header("Technology Detector", "Fingerprint website stack")
        url = ask("Enter URL (including https://)")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                body = resp.read().decode('utf-8', errors='ignore')
                headers_dict = {k.lower(): v for k, v in resp.headers.items()}
                console.print(f"\n  [bold cyan]Detected Technologies:[/bold cyan]\n")
                if 'server' in headers_dict:
                    console.print(f"  [yellow]Server:[/yellow] {headers_dict['server']}")
                if 'x-powered-by' in headers_dict:
                    console.print(f"  [yellow]Powered By:[/yellow] {headers_dict['x-powered-by']}")
                techs = {
                    "React": ["react", "reactDOM", "__NEXT_DATA__"],
                    "Vue.js": ["vue.js", "vue.min.js", "__vue__"],
                    "Angular": ["ng-version", "angular.js", "ng-app"],
                    "jQuery": ["jquery", "jQuery"],
                    "Bootstrap": ["bootstrap.css", "bootstrap.min.css"],
                    "Tailwind CSS": ["tailwindcss", "tailwind.css"],
                    "WordPress": ["wp-content", "wp-includes", "wordpress"],
                    "Shopify": ["cdn.shopify.com", "Shopify.theme"],
                    "Next.js": ["__NEXT_DATA__", "_next/"],
                    "Laravel": ["laravel", "csrf-token"],
                    "Django": ["csrfmiddlewaretoken", "django"],
                    "PHP": [".php", "PHPSESSID"],
                    "ASP.NET": ["__VIEWSTATE", "asp.net", ".aspx"],
                    "Cloudflare": ["cloudflare", "cf-ray"],
                    "Google Analytics": ["google-analytics.com", "gtag("],
                    "Google Tag Manager": ["googletagmanager.com"],
                    "Font Awesome": ["font-awesome", "fontawesome"],
                }
                found = []
                for tech, markers in techs.items():
                    for marker in markers:
                        if marker.lower() in body.lower() or marker.lower() in str(headers_dict).lower():
                            found.append(tech)
                            break
                for tech in found:
                    console.print(f"  [green]✓[/green] {tech}")
                if not found:
                    console.print("  [dim]No common technologies detected[/dim]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        pause()
        break


def robots_sitemap_viewer():
    """View robots.txt and sitemap.xml"""
    while True:
        header("Robots & Sitemap Viewer", "Check crawl rules & sitemap")
        domain = ask("Domain (e.g., example.com)")
        if not domain.startswith("http"):
            domain = "https://" + domain
        opts = ["View robots.txt", "View sitemap.xml", "Check Disallowed Paths"]
        sel = numbered_menu("View", opts)
        if sel == -1: return
        header("Robots & Sitemap", opts[sel])
        if sel == 0:
            try:
                url = f"{domain}/robots.txt"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    console.print(f"\n  [bold cyan]{url}[/bold cyan]\n")
                    console.print(content)
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 1:
            try:
                url = f"{domain}/sitemap.xml"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    console.print(f"\n  [bold cyan]{url}[/bold cyan]\n")
                    urls = re.findall(r'<loc>(.*?)</loc>', content)
                    if urls:
                        for u in urls[:30]:
                            console.print(f"  [dim]{u}[/dim]")
                        if len(urls) > 30:
                            console.print(f"\n  [dim]... and {len(urls)-30} more URLs[/dim]")
                    else:
                        console.print(content[:2000])
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        elif sel == 2:
            try:
                url = f"{domain}/robots.txt"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    content = resp.read().decode('utf-8', errors='ignore')
                    disallowed = re.findall(r'Disallow:\s*(.*)', content)
                    console.print(f"\n  [bold cyan]Disallowed Paths:[/bold cyan]\n")
                    for path in disallowed:
                        if path.strip():
                            console.print(f"  [red]✗[/red] {path.strip()}")
                    if not disallowed:
                        console.print("  [green]No disallowed paths[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
        pause()


def wayback_checker():
    """Check Wayback Machine archives for a URL"""
    while True:
        header("Wayback Machine Checker", "View archived versions")
        url = ask("Enter URL to check")
        console.print("  [yellow]Querying Wayback Machine...[/yellow]")
        try:
            api_url = f"https://archive.org/wayback/available?url={urllib.parse.quote(url)}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if data.get("archived_snapshots", {}).get("closest"):
                    snap = data["archived_snapshots"]["closest"]
                    console.print(f"\n  [bold cyan]Archive Found:[/bold cyan]\n")
                    console.print(f"  [bold]URL:[/bold]      {snap.get('url', 'N/A')}")
                    console.print(f"  [bold]Timestamp:[/bold] {snap.get('timestamp', 'N/A')}")
                    console.print(f"  [bold]Status:[/bold]    {snap.get('status', 'N/A')}")
                    console.print(f"  [bold]Available:[/bold] {'[green]Yes[/green]' if snap.get('available') else '[red]No[/red]'}")
                else:
                    console.print(f"  [dim]No archives found for {url}[/dim]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        pause()
        break


def link_extractor():
    """Extract all links from a webpage"""
    while True:
        header("Link Extractor", "Pull all links from a page")
        url = ask("Enter URL (including https://)")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                body = resp.read().decode('utf-8', errors='ignore')
                links = re.findall(r'href=["\']([^"\']+)["\']', body)
                internal = [l for l in links if l.startswith('/') or url.split('/')[2] in l]
                external = [l for l in links if l.startswith('http') and url.split('/')[2] not in l]
                console.print(f"\n  [bold cyan]Internal Links ({len(internal)}):[/bold cyan]\n")
                for l in internal[:20]:
                    console.print(f"  [dim]{l}[/dim]")
                if len(internal) > 20:
                    console.print(f"  [dim]... +{len(internal)-20} more[/dim]")
                console.print(f"\n  [bold yellow]External Links ({len(external)}):[/bold yellow]\n")
                for l in external[:20]:
                    console.print(f"  [yellow]{l}[/yellow]")
                if len(external) > 20:
                    console.print(f"  [dim]... +{len(external)-20} more[/dim]")
                console.print(f"\n  [bold]Total: {len(links)} links[/bold]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
        pause()
        break



def cron_builder():
    """Build cron expressions interactively"""
    while True:
        header("Cron Builder", "Build cron/scheduled task expressions")
        opts = [
            "Build Cron Expression",
            "Explain Cron Expression",
            "Common Cron Templates",
        ]
        sel = numbered_menu("Cron Builder", opts)
        if sel == -1: return
        header("Cron Builder", opts[sel])
        if sel == 0:
            console.print("  [dim]Format: minute hour day month weekday[/dim]\n")
            minute   = ask("Minute (0-59, */5, *)", "*")
            hour     = ask("Hour (0-23, */2, *)", "*")
            day      = ask("Day of month (1-31, *)", "*")
            month    = ask("Month (1-12, *)", "*")
            weekday  = ask("Day of week (0-6, Sun=0, *)", "*")
            expr = f"{minute} {hour} {day} {month} {weekday}"
            console.print(f"\n  [bold cyan]Cron Expression:[/bold cyan]")
            console.print(f"  [bold yellow]{expr}[/bold yellow]")
            console.print(f"\n  [dim]Usage: {expr} /path/to/command[/dim]")
        elif sel == 1:
            expr = ask("Enter cron expression (5 fields)")
            parts = expr.split()
            if len(parts) != 5:
                console.print("  [red]Need 5 fields: minute hour day month weekday[/red]")
            else:
                labels = ["Minute", "Hour", "Day of Month", "Month", "Day of Week"]
                console.print(f"\n  [bold cyan]Breakdown:[/bold cyan]\n")
                for label, val in zip(labels, parts):
                    if val == "*":
                        desc = "every"
                    elif val.startswith("*/"):
                        desc = f"every {val[2:]}"
                    elif "," in val:
                        desc = f"at {val}"
                    elif "-" in val:
                        desc = f"range {val}"
                    else:
                        desc = f"at {val}"
                    console.print(f"  [yellow]{label:<15}[/yellow] {val:<10} → {desc}")
        elif sel == 2:
            templates = [
                ("Every minute",          "* * * * *"),
                ("Every 5 minutes",       "*/5 * * * *"),
                ("Every hour",            "0 * * * *"),
                ("Every day at midnight", "0 0 * * *"),
                ("Every day at 6 AM",     "0 6 * * *"),
                ("Every Monday at 9 AM",  "0 9 * * 1"),
                ("Every 1st of month",    "0 0 1 * *"),
                ("Weekdays at 8 AM",      "0 8 * * 1-5"),
                ("Every 15 minutes",      "*/15 * * * *"),
                ("Twice a day",           "0 0,12 * * *"),
            ]
            console.print(f"\n  [bold cyan]Common Cron Templates:[/bold cyan]\n")
            for desc, expr in templates:
                console.print(f"  [yellow]{expr:<20}[/yellow] {desc}")
        pause()


def lorem_generator():
    """Generate placeholder text for development"""
    while True:
        header("Lorem Generator", "Placeholder text for dev/design")
        opts = ["Paragraphs", "Sentences", "Words", "JSON Placeholder Data", "HTML Boilerplate"]
        sel = numbered_menu("Generate", opts)
        if sel == -1: return
        header("Lorem Generator", opts[sel])
        base = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua Ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur Excepteur sint occaecat cupidatat non proident sunt in culpa qui officia deserunt mollit anim id est laborum".split()
        if sel == 0:
            count = int(ask("Number of paragraphs", "3"))
            for i in range(count):
                words = random.sample(base, min(40, len(base)))
                para = " ".join(words).capitalize() + "."
                console.print(f"\n  {para}")
        elif sel == 1:
            count = int(ask("Number of sentences", "5"))
            for i in range(count):
                length = random.randint(8, 15)
                words = random.sample(base, length)
                console.print(f"  {' '.join(words).capitalize()}.")
        elif sel == 2:
            count = int(ask("Number of words", "50"))
            words = [random.choice(base) for _ in range(count)]
            console.print(f"\n  {' '.join(words)}")
        elif sel == 3:
            count = int(ask("Number of entries", "5"))
            console.print(f"\n  [bold cyan]JSON Placeholder:[/bold cyan]\n")
            data = []
            for i in range(count):
                data.append({
                    "id": i + 1,
                    "name": f"User {i+1}",
                    "email": f"user{i+1}@example.com",
                    "active": random.choice([True, False]),
                    "score": random.randint(1, 100)
                })
            console.print(json.dumps(data, indent=2))
        elif sel == 4:
            title = ask("Page title", "My Page")
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; line-height: 1.6; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
</body>
</html>"""
            console.print(f"\n{html}")
        pause()


def diff_tool():
    """Compare two text inputs or files"""
    while True:
        header("Diff Tool", "Compare text or files")
        opts = ["Compare Two Texts", "Compare Two Files"]
        sel = numbered_menu("Diff", opts)
        if sel == -1: return
        header("Diff Tool", opts[sel])
        if sel == 0:
            console.print("  [dim]Enter first text (CTRL+Z then ENTER to finish):[/dim]")
            lines1 = []
            try:
                while True: lines1.append(input())
            except EOFError: pass
            console.print("  [dim]Enter second text (CTRL+Z then ENTER to finish):[/dim]")
            lines2 = []
            try:
                while True: lines2.append(input())
            except EOFError: pass
        elif sel == 1:
            file1 = ask("First file path")
            file2 = ask("Second file path")
            try:
                with open(file1, 'r') as f: lines1 = f.read().splitlines()
                with open(file2, 'r') as f: lines2 = f.read().splitlines()
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
                pause()
                continue
        console.print(f"\n  [bold cyan]Diff Result:[/bold cyan]\n")
        max_lines = max(len(lines1), len(lines2))
        diffs = 0
        for i in range(max_lines):
            l1 = lines1[i] if i < len(lines1) else ""
            l2 = lines2[i] if i < len(lines2) else ""
            if l1 == l2:
                console.print(f"  [dim]{i+1:>4} │ {l1}[/dim]")
            else:
                console.print(f"  [red]{i+1:>4} - {l1}[/red]")
                console.print(f"  [green]{i+1:>4} + {l2}[/green]")
                diffs += 1
        console.print(f"\n  [bold]{diffs} difference(s) found[/bold]")
        pause()
        break


def snippet_manager():
    """Save and retrieve code snippets"""
    snippets_file = os.path.join(os.path.expanduser("~"), ".devtool_snippets.json")
    def load_snippets():
        if os.path.exists(snippets_file):
            with open(snippets_file, 'r') as f:
                return json.load(f)
        return []
    def save_snippets(data):
        with open(snippets_file, 'w') as f:
            json.dump(data, f, indent=2)
    while True:
        header("Snippet Manager", "Save & reuse code snippets")
        opts = ["View Snippets", "Add Snippet", "Search Snippets", "Delete Snippet", "Export All"]
        sel = numbered_menu("Snippets", opts)
        if sel == -1: return
        header("Snippets", opts[sel])
        snippets = load_snippets()
        if sel == 0:
            if not snippets:
                console.print("  [dim]No snippets saved yet[/dim]")
            else:
                for i, s in enumerate(snippets):
                    console.print(f"\n  [bold cyan]#{i+1}[/bold cyan] [yellow]{s['title']}[/yellow] [dim]({s.get('lang', 'text')})[/dim]")
                    console.print(f"  {s['code'][:100]}{'...' if len(s['code']) > 100 else ''}")
                view = ask("View full snippet # (or blank)", "")
                if view.isdigit() and 1 <= int(view) <= len(snippets):
                    s = snippets[int(view)-1]
                    console.print(f"\n  [bold yellow]{s['title']}[/bold yellow]\n")
                    console.print(s['code'])
        elif sel == 1:
            title = ask("Snippet title")
            lang = ask("Language", "python")
            console.print("  [dim]Paste code (CTRL+Z then ENTER to finish):[/dim]")
            lines = []
            try:
                while True: lines.append(input())
            except EOFError: pass
            code = "\n".join(lines)
            snippets.append({"title": title, "lang": lang, "code": code})
            save_snippets(snippets)
            console.print(f"  [green]✓ Saved '{title}'[/green]")
        elif sel == 2:
            query = ask("Search term").lower()
            found = [s for s in snippets if query in s['title'].lower() or query in s['code'].lower()]
            if found:
                for s in found:
                    console.print(f"\n  [yellow]{s['title']}[/yellow] [dim]({s.get('lang', 'text')})[/dim]")
                    console.print(f"  {s['code'][:150]}")
            else:
                console.print(f"  [dim]No snippets matching '{query}'[/dim]")
        elif sel == 3:
            if snippets:
                for i, s in enumerate(snippets):
                    console.print(f"  [bold]{i+1}[/bold] {s['title']}")
                idx = ask("Delete #")
                if idx.isdigit() and 1 <= int(idx) <= len(snippets):
                    removed = snippets.pop(int(idx)-1)
                    save_snippets(snippets)
                    console.print(f"  [green]✓ Deleted '{removed['title']}'[/green]")
        elif sel == 4:
            if snippets:
                export_path = ask("Export path", "snippets_export.json")
                with open(export_path, 'w') as f:
                    json.dump(snippets, f, indent=2)
                console.print(f"  [green]✓ Exported {len(snippets)} snippets to {export_path}[/green]")
            else:
                console.print("  [dim]No snippets to export[/dim]")
        pause()


def color_picker():
    """Convert between color formats (hex, rgb, hsl) for CSS"""
    while True:
        header("Color Picker", "Convert HEX / RGB / HSL for CSS")
        opts = ["HEX to RGB", "RGB to HEX", "Random Color Palette", "CSS Color Names"]
        sel = numbered_menu("Colors", opts)
        if sel == -1: return
        header("Color Picker", opts[sel])
        if sel == 0:
            hex_val = ask("HEX color (e.g., #ff5733 or ff5733)")
            hex_val = hex_val.lstrip('#')
            if len(hex_val) == 6:
                r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
                console.print(f"\n  [bold cyan]Color Conversion:[/bold cyan]")
                console.print(f"  HEX: [yellow]#{hex_val}[/yellow]")
                console.print(f"  RGB: [yellow]rgb({r}, {g}, {b})[/yellow]")
                console.print(f"  CSS: [yellow]color: #{hex_val};[/yellow]")
            else:
                console.print("  [red]Invalid hex color[/red]")
        elif sel == 1:
            r = int(ask("Red (0-255)"))
            g = int(ask("Green (0-255)"))
            b = int(ask("Blue (0-255)"))
            hex_val = f"#{r:02x}{g:02x}{b:02x}"
            console.print(f"\n  [bold cyan]Color Conversion:[/bold cyan]")
            console.print(f"  RGB: [yellow]rgb({r}, {g}, {b})[/yellow]")
            console.print(f"  HEX: [yellow]{hex_val}[/yellow]")
            console.print(f"  CSS: [yellow]background-color: {hex_val};[/yellow]")
        elif sel == 2:
            count = int(ask("Number of colors", "5"))
            console.print(f"\n  [bold cyan]Random Palette:[/bold cyan]\n")
            for _ in range(count):
                r, g, b = random.randint(0,255), random.randint(0,255), random.randint(0,255)
                hex_val = f"#{r:02x}{g:02x}{b:02x}"
                console.print(f"  [on #{r:02x}{g:02x}{b:02x}]      [/on #{r:02x}{g:02x}{b:02x}]  {hex_val}  rgb({r},{g},{b})")
        elif sel == 3:
            names = {"red":"#ff0000","blue":"#0000ff","green":"#008000","black":"#000000",
                     "white":"#ffffff","orange":"#ffa500","purple":"#800080","pink":"#ffc0cb",
                     "cyan":"#00ffff","yellow":"#ffff00","gray":"#808080","navy":"#000080",
                     "teal":"#008080","coral":"#ff7f50","salmon":"#fa8072","gold":"#ffd700"}
            for name, hex_val in names.items():
                console.print(f"  [yellow]{name:<12}[/yellow] {hex_val}")
        pause()


def file_watcher():
    """Watch a directory for file changes"""
    while True:
        header("File Watcher", "Monitor directory for changes")
        folder = ask("Directory to watch", ".")
        if not os.path.isdir(folder):
            console.print(f"  [red]Not a valid directory[/red]")
            pause()
            continue
        console.print(f"  [yellow]Watching {os.path.abspath(folder)}... (CTRL+C to stop)[/yellow]\n")
        def snapshot(path):
            files = {}
            for dp, dn, fns in os.walk(path):
                for f in fns:
                    fp = os.path.join(dp, f)
                    try:
                        files[fp] = os.path.getmtime(fp)
                    except Exception:
                        pass
            return files
        prev = snapshot(folder)
        try:
            while True:
                time.sleep(1)
                curr = snapshot(folder)
                for f in curr:
                    if f not in prev:
                        console.print(f"  [green]+ NEW:[/green] {f}")
                for f in prev:
                    if f not in curr:
                        console.print(f"  [red]- DEL:[/red] {f}")
                for f in curr:
                    if f in prev and curr[f] != prev[f]:
                        console.print(f"  [yellow]~ MOD:[/yellow] {f}")
                prev = curr
        except KeyboardInterrupt:
            console.print(f"\n  [dim]Stopped watching[/dim]")
        pause()
        break



def page_file_optimizer():
    """Configure Windows virtual memory / page file settings."""
    while True:
        header("Page File Optimizer", "Configure virtual memory for performance")
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Setting", width=30)
        t.add_column("Value", width=30)
        t.add_row("Physical RAM", fmt_bytes(mem.total))
        t.add_row("Page File Used", fmt_bytes(swap.used))
        t.add_row("Page File Free", fmt_bytes(swap.free))
        t.add_row("Page File Total", fmt_bytes(swap.total))
        console.print(t)
        console.print()
        items = [
            "Show current page file config",
            "Set page file to 1.5x RAM (recommended)",
            "Set page file to 2x RAM (heavy workloads)",
            "Set custom page file size",
            "Reset to system managed",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-CimInstance Win32_PageFileSetting | Format-List *")
            console.print(f"\n{out or '  [dim]System managed (no custom settings)[/dim]'}")
        elif c == 1:
            ram_mb = mem.total // (1024*1024)
            init = int(ram_mb * 1.5)
            mx = int(ram_mb * 2)
            run_ps(f'$pf = Get-CimInstance Win32_PageFileSetting; if($pf){{$pf | Remove-CimInstance}}; '
                   f'New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name="C:\\pagefile.sys"; InitialSize={init}; MaximumSize={mx}}}')
            console.print(f"  [green]✓ Page file set to {init}MB–{mx}MB (restart required)[/green]")
        elif c == 2:
            ram_mb = mem.total // (1024*1024)
            init = int(ram_mb * 2)
            mx = int(ram_mb * 3)
            run_ps(f'$pf = Get-CimInstance Win32_PageFileSetting; if($pf){{$pf | Remove-CimInstance}}; '
                   f'New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name="C:\\pagefile.sys"; InitialSize={init}; MaximumSize={mx}}}')
            console.print(f"  [green]✓ Page file set to {init}MB–{mx}MB (restart required)[/green]")
        elif c == 3:
            init = ask("Initial size (MB)")
            mx = ask("Maximum size (MB)")
            if init.isdigit() and mx.isdigit():
                run_ps(f'$pf = Get-CimInstance Win32_PageFileSetting; if($pf){{$pf | Remove-CimInstance}}; '
                       f'New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name="C:\\pagefile.sys"; InitialSize={init}; MaximumSize={mx}}}')
                console.print(f"  [green]✓ Page file set to {init}MB–{mx}MB (restart required)[/green]")
        elif c == 4:
            run_ps('$pf = Get-CimInstance Win32_PageFileSetting; if($pf){$pf | Remove-CimInstance}')
            console.print("  [green]✓ Reset to system managed (restart required)[/green]")
        pause()


def system_timer_resolution():
    """Set system timer resolution for gaming/low-latency."""
    while True:
        header("System Timer Resolution", "Lower = more responsive, higher power use")
        items = [
            "Show current timer resolution",
            "Set high resolution (0.5ms) — best for gaming",
            "Set medium resolution (1ms)",
            "Restore default (15.6ms)",
            "Create auto-start timer service",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps(
                '[System.Diagnostics.Process]::GetCurrentProcess().PriorityClass; '
                '$sig = \'[DllImport("ntdll.dll")] public static extern int NtQueryTimerResolution(out int min, out int max, out int cur);\'; '
                '$nt = Add-Type -MemberDefinition $sig -Name NtDll -Namespace Win32 -PassThru; '
                '$min=$max=$cur=0; [void]$nt::NtQueryTimerResolution([ref]$min,[ref]$max,[ref]$cur); '
                '"Min: $($min/10000)ms  Max: $($max/10000)ms  Current: $($cur/10000)ms"'
            )
            console.print(f"\n  {out}")
        elif c == 1:
            run_ps(
                '$sig = \'[DllImport("ntdll.dll")] public static extern int NtSetTimerResolution(int res, bool set, out int cur);\'; '
                '$nt = Add-Type -MemberDefinition $sig -Name NtDll2 -Namespace Win32 -PassThru; '
                '$cur=0; [void]$nt::NtSetTimerResolution(5000, $true, [ref]$cur); '
                '"Set to $($cur/10000)ms"'
            )
            console.print("  [green]✓ Timer set to 0.5ms (active this session)[/green]")
        elif c == 2:
            run_ps(
                '$sig = \'[DllImport("ntdll.dll")] public static extern int NtSetTimerResolution(int res, bool set, out int cur);\'; '
                '$nt = Add-Type -MemberDefinition $sig -Name NtDll3 -Namespace Win32 -PassThru; '
                '$cur=0; [void]$nt::NtSetTimerResolution(10000, $true, [ref]$cur)'
            )
            console.print("  [green]✓ Timer set to 1ms (active this session)[/green]")
        elif c == 3:
            run_ps(
                '$sig = \'[DllImport("ntdll.dll")] public static extern int NtSetTimerResolution(int res, bool set, out int cur);\'; '
                '$nt = Add-Type -MemberDefinition $sig -Name NtDll4 -Namespace Win32 -PassThru; '
                '$cur=0; [void]$nt::NtSetTimerResolution(156250, $true, [ref]$cur)'
            )
            console.print("  [green]✓ Timer restored to 15.6ms default[/green]")
        elif c == 4:
            reg = r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel"
            run_cmd(f'reg add "{reg}" /v GlobalTimerResolutionRequests /t REG_DWORD /d 1 /f')
            console.print("  [green]✓ Registry key set for persistent timer (restart required)[/green]")
        pause()


def usb_power_optimizer():
    """Disable USB selective suspend and power management."""
    while True:
        header("USB Power Management", "Prevent USB devices from sleeping")
        items = [
            "Disable USB selective suspend (power plan)",
            "Disable USB hub power management (all hubs)",
            "Disable USB auto-suspend in registry",
            "Re-enable USB power saving",
            "Show USB device power states",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            run_ps("powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0; "
                   "powercfg /SETDCVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0; "
                   "powercfg /SETACTIVE SCHEME_CURRENT")
            console.print("  [green]✓ USB selective suspend disabled[/green]")
        elif c == 1:
            run_ps(
                'Get-PnpDevice -Class USB | Where-Object {$_.FriendlyName -like "*Hub*"} | ForEach-Object { '
                '$id = $_.InstanceId; '
                'Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$id\\Device Parameters" '
                '-Name EnhancedPowerManagementEnabled -Value 0 -ErrorAction SilentlyContinue '
                '}'
            )
            console.print("  [green]✓ USB hub power management disabled[/green]")
        elif c == 2:
            run_cmd('reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\USB" /v DisableSelectiveSuspend /t REG_DWORD /d 1 /f')
            console.print("  [green]✓ USB auto-suspend disabled in registry[/green]")
        elif c == 3:
            run_ps("powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 1; "
                   "powercfg /SETACTIVE SCHEME_CURRENT")
            run_cmd('reg delete "HKLM\\SYSTEM\\CurrentControlSet\\Services\\USB" /v DisableSelectiveSuspend /f 2>nul')
            console.print("  [green]✓ USB power saving re-enabled[/green]")
        elif c == 4:
            out = run_ps("Get-PnpDevice -Class USB | Select-Object Status, FriendlyName, InstanceId | Format-Table -AutoSize")
            console.print(f"\n{out}")
        pause()


def audio_latency_optimizer():
    """Optimize audio buffer/latency for gaming and production."""
    while True:
        header("Audio Latency Optimizer", "Reduce audio latency and improve responsiveness")
        items = [
            "Show audio devices",
            "Set exclusive mode priority (all devices)",
            "Reduce audio buffer size (low latency)",
            "Disable audio enhancements",
            "Set high-priority audio thread scheduling",
            "Restore default audio settings",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-PnpDevice -Class AudioEndpoint | Where-Object Status -eq 'OK' | "
                         "Select-Object FriendlyName, Status | Format-Table -AutoSize")
            console.print(f"\n{out}")
        elif c == 1:
            reg = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
            run_ps(f'Get-ChildItem "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render" -Recurse | '
                   f'Where-Object {{ $_.PSChildName -eq "Properties" }} | ForEach-Object {{ '
                   f'Set-ItemProperty -Path $_.PSPath -Name "{{b3f8fa53-0004-438e-9003-51a46e139bfc}},3" -Value 0 -ErrorAction SilentlyContinue }}')
            console.print("  [green]✓ Exclusive mode priority set[/green]")
        elif c == 2:
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 0 /f')
            console.print("  [green]✓ System responsiveness set to 0 (minimum latency)[/green]")
        elif c == 3:
            run_ps('Get-ChildItem "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render" -Recurse | '
                   'Where-Object { $_.PSChildName -eq "FxProperties" } | ForEach-Object { '
                   'Set-ItemProperty -Path $_.PSPath -Name "{d04e05a6-594b-4fb6-a80d-01af5eed7d1d},5" -Value 1 -ErrorAction SilentlyContinue }')
            console.print("  [green]✓ Audio enhancements disabled[/green]")
        elif c == 4:
            reg = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Pro Audio"
            run_cmd(f'reg add "{reg}" /v "Scheduling Category" /t REG_SZ /d "High" /f')
            run_cmd(f'reg add "{reg}" /v Priority /t REG_DWORD /d 1 /f')
            run_cmd(f'reg add "{reg}" /v "SFIO Priority" /t REG_SZ /d "High" /f')
            console.print("  [green]✓ Pro Audio thread priority elevated[/green]")
        elif c == 5:
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile" /v SystemResponsiveness /t REG_DWORD /d 20 /f')
            console.print("  [green]✓ Audio settings restored to defaults[/green]")
        pause()


def windows_search_optimizer():
    """Control Windows Search indexing service."""
    while True:
        header("Windows Search Optimizer", "Reduce disk I/O from indexing")
        out = run_ps("Get-Service WSearch -ErrorAction SilentlyContinue | Select-Object Status, StartType | Format-List")
        console.print(f"  [dim]Current: {out.strip() if out else 'Unknown'}[/dim]\n")
        items = [
            "Disable Windows Search service",
            "Set to Manual (only when needed)",
            "Re-enable Windows Search",
            "Clear search index (reclaim space)",
            "Show index size / locations",
            "Reduce indexer priority",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            run_cmd("sc config WSearch start= disabled")
            run_cmd("sc stop WSearch")
            console.print("  [green]✓ Windows Search disabled[/green]")
        elif c == 1:
            run_cmd("sc config WSearch start= demand")
            run_cmd("sc stop WSearch")
            console.print("  [green]✓ Windows Search set to manual[/green]")
        elif c == 2:
            run_cmd("sc config WSearch start= delayed-auto")
            run_cmd("sc start WSearch")
            console.print("  [green]✓ Windows Search re-enabled[/green]")
        elif c == 3:
            idx_path = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                                    "Microsoft", "Search", "Data", "Applications", "Windows")
            if os.path.isdir(idx_path):
                size = sum(os.path.getsize(os.path.join(dp, f))
                          for dp, _, fns in os.walk(idx_path) for f in fns)
                run_cmd("sc stop WSearch")
                run_ps(f'Remove-Item -Path "{idx_path}\\*" -Recurse -Force -ErrorAction SilentlyContinue')
                console.print(f"  [green]✓ Cleared {fmt_bytes(size)} of search index[/green]")
            else:
                console.print("  [dim]Index path not found[/dim]")
        elif c == 4:
            out = run_ps("Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows Search' -ErrorAction SilentlyContinue | "
                         "Select-Object DataDirectory, SetupCompletedSuccessfully | Format-List")
            console.print(f"\n{out}")
        elif c == 5:
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows Search" /v CoreCount /t REG_DWORD /d 1 /f')
            console.print("  [green]✓ Indexer limited to 1 core[/green]")
        pause()


def shader_cache_manager():
    """Manage GPU shader caches to fix stutter and reclaim space."""
    while True:
        header("Shader Cache Manager", "Clear stale GPU shader caches")
        nvidia_cache = os.path.join(LAD, "NVIDIA", "DXCache")
        nvidia_gl = os.path.join(LAD, "NVIDIA", "GLCache")
        dx_cache = os.path.join(LAD, "D3DSCache")
        amd_cache = os.path.join(LAD, "AMD", "DxCache")
        intel_cache = os.path.join(LAD, "Intel", "ShaderCache")
        pipe_cache = os.path.join(LAD, "NVIDIA Corporation", "NV_Cache")
        caches = [
            ("NVIDIA DXCache",     nvidia_cache),
            ("NVIDIA GLCache",     nvidia_gl),
            ("NVIDIA PipelineCache", pipe_cache),
            ("DirectX Shader Cache", dx_cache),
            ("AMD DxCache",        amd_cache),
            ("Intel ShaderCache",  intel_cache),
        ]
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Cache", width=26)
        t.add_column("Size", width=12, justify="right")
        t.add_column("Status", width=12)
        total = 0
        for name, path in caches:
            if os.path.isdir(path):
                size = sum(os.path.getsize(os.path.join(dp, f))
                          for dp, _, fns in os.walk(path) for f in fns)
                total += size
                t.add_row(name, fmt_bytes(size), "[green]Found[/green]")
            else:
                t.add_row(name, "—", "[dim]N/A[/dim]")
        console.print(t)
        console.print(f"  [bold]Total: {fmt_bytes(total)}[/bold]\n")
        items = [
            "Clear all shader caches",
            "Clear NVIDIA caches only",
            "Clear DirectX cache only",
            "Disable DirectX shader cache (registry)",
            "Re-enable DirectX shader cache",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            cleared = 0
            for name, path in caches:
                if os.path.isdir(path):
                    for dp, _, fns in os.walk(path):
                        for f in fns:
                            try: os.remove(os.path.join(dp, f)); cleared += 1
                            except Exception:
                                pass
            console.print(f"  [green]✓ Cleared {cleared} cached files[/green]")
        elif c == 1:
            for path in (nvidia_cache, nvidia_gl, pipe_cache):
                if os.path.isdir(path):
                    for dp, _, fns in os.walk(path):
                        for f in fns:
                            try: os.remove(os.path.join(dp, f))
                            except Exception:
                                pass
            console.print("  [green]✓ NVIDIA caches cleared[/green]")
        elif c == 2:
            if os.path.isdir(dx_cache):
                for dp, _, fns in os.walk(dx_cache):
                    for f in fns:
                        try: os.remove(os.path.join(dp, f))
                        except Exception:
                            pass
            console.print("  [green]✓ DirectX shader cache cleared[/green]")
        elif c == 3:
            run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\DirectX" /v DisableShaderCache /t REG_DWORD /d 1 /f')
            console.print("  [green]✓ DirectX shader cache disabled[/green]")
        elif c == 4:
            run_cmd('reg delete "HKLM\\SOFTWARE\\Microsoft\\DirectX" /v DisableShaderCache /f 2>nul')
            console.print("  [green]✓ DirectX shader cache re-enabled[/green]")
        pause()


def interrupt_affinity_tool():
    """View and configure device interrupt CPU affinity."""
    while True:
        header("Interrupt Affinity", "Pin device interrupts to specific CPU cores")
        items = [
            "Show MSI-capable devices",
            "Enable MSI mode for network adapters",
            "Enable MSI mode for GPU",
            "Enable MSI mode for USB controllers",
            "Set network interrupt affinity to Core 0",
            "Show current interrupt assignments",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps(
                'Get-ChildItem "HKLM:\\SYSTEM\\CurrentControlSet\\Enum" -Recurse -ErrorAction SilentlyContinue | '
                'Where-Object { $_.PSChildName -eq "MessageSignaledInterruptProperties" } | '
                'Select-Object -First 20 | ForEach-Object { '
                '$parent = Split-Path $_.PSPath -Parent; '
                '$name = (Get-ItemProperty "$parent\\..\\..").FriendlyName; '
                '$msi = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).MSISupported; '
                '"$name -> MSI: $msi" }'
            )
            console.print(f"\n{out or '  [dim]No MSI devices found[/dim]'}")
        elif c == 1:
            run_ps(
                'Get-NetAdapter | ForEach-Object { '
                '$path = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($_.PnPDeviceID)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"; '
                'if (Test-Path $path) { Set-ItemProperty -Path $path -Name MSISupported -Value 1 -ErrorAction SilentlyContinue; '
                'Write-Host "Enabled MSI for $($_.Name)" } }'
            )
            console.print("  [green]✓ MSI mode enabled for network adapters (restart required)[/green]")
        elif c == 2:
            run_ps(
                'Get-PnpDevice -Class Display | Where-Object Status -eq OK | ForEach-Object { '
                '$path = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($_.InstanceId)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"; '
                'if (Test-Path $path) { Set-ItemProperty -Path $path -Name MSISupported -Value 1; '
                'Write-Host "Enabled MSI for $($_.FriendlyName)" } }'
            )
            console.print("  [green]✓ MSI mode enabled for GPU (restart required)[/green]")
        elif c == 3:
            run_ps(
                'Get-PnpDevice -Class USB | Where-Object Status -eq OK | ForEach-Object { '
                '$path = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($_.InstanceId)\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"; '
                'if (Test-Path $path) { Set-ItemProperty -Path $path -Name MSISupported -Value 1 -ErrorAction SilentlyContinue } }'
            )
            console.print("  [green]✓ MSI mode enabled for USB controllers[/green]")
        elif c == 4:
            run_ps(
                'Get-NetAdapter | ForEach-Object { '
                '$path = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($_.PnPDeviceID)\\Device Parameters\\Interrupt Management\\Affinity Policy"; '
                'if (!(Test-Path $path)) { New-Item -Path $path -Force | Out-Null } '
                'Set-ItemProperty -Path $path -Name DevicePolicy -Value 4; '
                'Set-ItemProperty -Path $path -Name AssignmentSetOverride -Value ([byte[]](1)) }'
            )
            console.print("  [green]✓ Network interrupts pinned to Core 0 (restart required)[/green]")
        elif c == 5:
            out = run_ps(
                'Get-NetAdapterAdvancedProperty -ErrorAction SilentlyContinue | '
                'Where-Object { $_.RegistryKeyword -like "*RSS*" -or $_.RegistryKeyword -like "*Interrupt*" } | '
                'Select-Object Name, DisplayName, DisplayValue | Format-Table -AutoSize'
            )
            console.print(f"\n{out or '  [dim]No interrupt properties found[/dim]'}")
        pause()


def boot_config_tweaks():
    """BCDEdit boot configuration optimizations."""
    while True:
        header("Boot Configuration (BCDEdit)", "Optimize boot settings")
        out = run_ps("bcdedit /enum {current}")
        console.print(f"  [dim]Current boot config:[/dim]\n{out[:1500] if out else '  Unknown'}\n")
        items = [
            "Disable boot GUI animation (faster boot)",
            "Set boot timeout to 3 seconds",
            "Set boot timeout to 0 (instant)",
            "Enable No-Execute (NX) Always On",
            "Disable Hyper-V (bare-metal gaming)",
            "Re-enable Hyper-V",
            "Set max processors for boot",
            "Restore default boot GUI",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            run_cmd("bcdedit /set {current} quietboot yes")
            run_cmd("bcdedit /set {current} bootux disabled")
            console.print("  [green]✓ Boot GUI disabled (faster boot)[/green]")
        elif c == 1:
            run_cmd("bcdedit /timeout 3")
            console.print("  [green]✓ Boot timeout set to 3s[/green]")
        elif c == 2:
            run_cmd("bcdedit /timeout 0")
            console.print("  [green]✓ Boot timeout set to 0s[/green]")
        elif c == 3:
            run_cmd("bcdedit /set {current} nx AlwaysOn")
            console.print("  [green]✓ NX set to Always On[/green]")
        elif c == 4:
            run_cmd("bcdedit /set hypervisorlaunchtype off")
            console.print("  [green]✓ Hyper-V disabled (restart required)[/green]")
        elif c == 5:
            run_cmd("bcdedit /set hypervisorlaunchtype auto")
            console.print("  [green]✓ Hyper-V re-enabled (restart required)[/green]")
        elif c == 6:
            cores = os.cpu_count() or 4
            n = ask(f"Number of processors to use at boot (max {cores})")
            if n.isdigit() and 1 <= int(n) <= cores:
                run_cmd(f"bcdedit /set {{current}} numproc {n}")
                console.print(f"  [green]✓ Boot processors set to {n}[/green]")
        elif c == 7:
            run_cmd("bcdedit /deletevalue {current} quietboot")
            run_cmd("bcdedit /deletevalue {current} bootux")
            console.print("  [green]✓ Boot GUI restored to default[/green]")
        pause()



def system_restore_manager():
    """Create, list, and delete system restore points."""
    while True:
        header("System Restore Manager", "Manage Windows restore points")
        items = [
            "List existing restore points",
            "Create new restore point",
            "Check restore point storage usage",
            "Enable System Restore on C:",
            "Disable System Restore on C:",
            "Set max storage for restore points",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-ComputerRestorePoint | Sort-Object SequenceNumber -Descending | "
                         "Select-Object SequenceNumber, @{N='Date';E={$_.ConvertToDateTime($_.CreationTime)}}, Description | "
                         "Format-Table -AutoSize")
            console.print(f"\n{out or '  [dim]No restore points found[/dim]'}")
        elif c == 1:
            desc = ask("Description for restore point") or "raideds tool backup"
            out = run_ps(f'Checkpoint-Computer -Description "{desc}" -RestorePointType "MODIFY_SETTINGS" 2>&1')
            console.print(f"  [green]✓ Restore point created[/green]")
            if out: console.print(f"  [dim]{out}[/dim]")
        elif c == 2:
            out = run_ps("vssadmin list shadowstorage 2>&1")
            console.print(f"\n{out}")
        elif c == 3:
            run_ps("Enable-ComputerRestore -Drive 'C:\\'")
            console.print("  [green]✓ System Restore enabled on C:[/green]")
        elif c == 4:
            if confirm("Disable System Restore on C:?"):
                run_ps("Disable-ComputerRestore -Drive 'C:\\'")
                console.print("  [green]✓ System Restore disabled on C:[/green]")
        elif c == 5:
            pct = ask("Max % of disk for restore points (e.g. 5)")
            if pct.isdigit():
                run_cmd(f'vssadmin resize shadowstorage /for=C: /on=C: /maxsize={pct}%')
                console.print(f"  [green]✓ Max storage set to {pct}%[/green]")
        pause()


def certificate_viewer():
    """View installed system certificates."""
    while True:
        header("Certificate Manager", "View & export system certificates")
        items = [
            "List trusted root certificates",
            "List personal certificates",
            "List expired certificates",
            "Export certificate details to file",
            "Check certificate expiry (all stores)",
            "Show certificate store summary",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-ChildItem Cert:\\LocalMachine\\Root | "
                         "Select-Object Thumbprint, Subject, NotAfter | "
                         "Sort-Object NotAfter -Descending | Format-Table -AutoSize | Out-String -Width 200")
            console.print(f"\n{out[:3000]}")
        elif c == 1:
            out = run_ps("Get-ChildItem Cert:\\CurrentUser\\My | "
                         "Select-Object Thumbprint, Subject, NotAfter | Format-Table -AutoSize")
            console.print(f"\n{out or '  [dim]No personal certificates[/dim]'}")
        elif c == 2:
            out = run_ps("Get-ChildItem Cert:\\LocalMachine\\Root | Where-Object { $_.NotAfter -lt (Get-Date) } | "
                         "Select-Object Subject, NotAfter | Format-Table -AutoSize")
            console.print(f"\n{out or '  [dim]No expired certificates[/dim]'}")
        elif c == 3:
            path = os.path.join(HOME, "Desktop", "certificates.txt")
            run_ps(f"Get-ChildItem Cert:\\LocalMachine\\Root | "
                   f"Select-Object Thumbprint, Subject, NotBefore, NotAfter | "
                   f"Format-Table -AutoSize | Out-File -FilePath '{path}' -Width 300")
            console.print(f"  [green]✓ Exported to {path}[/green]")
        elif c == 4:
            out = run_ps(
                "$stores = @('Root','CA','My','Trust','TrustedPublisher'); "
                "foreach ($s in $stores) { "
                "$expiring = Get-ChildItem \"Cert:\\LocalMachine\\$s\" -ErrorAction SilentlyContinue | "
                "Where-Object { $_.NotAfter -lt (Get-Date).AddDays(30) -and $_.NotAfter -gt (Get-Date) }; "
                "if ($expiring) { Write-Host \"[$s] Expiring soon: $($expiring.Count)\" } }"
            )
            console.print(f"\n{out or '  [dim]No certificates expiring within 30 days[/dim]'}")
        elif c == 5:
            out = run_ps(
                "$stores = @('Root','CA','My','Trust','TrustedPublisher','Disallowed'); "
                "foreach ($s in $stores) { "
                "$count = (Get-ChildItem \"Cert:\\LocalMachine\\$s\" -ErrorAction SilentlyContinue).Count; "
                "Write-Host \"$s : $count certificates\" }"
            )
            console.print(f"\n{out}")
        pause()


def temp_file_monitor():
    """Real-time temp directory monitoring."""
    while True:
        header("Temp File Monitor", "Watch and manage temp file growth")
        tmp_dirs = [
            ("User Temp", os.environ.get("TEMP", "")),
            ("Windows Temp", os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")),
            ("Prefetch", os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Prefetch")),
        ]
        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("Location", width=22)
        t.add_column("Files", width=8, justify="right")
        t.add_column("Size", width=12, justify="right")
        t.add_column("Path", width=40, style="dim")
        for name, path in tmp_dirs:
            if os.path.isdir(path):
                count = sum(len(fns) for _, _, fns in os.walk(path))
                size = sum(os.path.getsize(os.path.join(dp, f))
                           for dp, _, fns in os.walk(path) for f in fns
                           if os.path.exists(os.path.join(dp, f)))
                t.add_row(name, str(count), fmt_bytes(size), path)
            else:
                t.add_row(name, "—", "—", path)
        console.print(t)
        console.print()
        items = [
            "Clean all temp directories",
            "Clean user temp only",
            "Clean Windows temp only",
            "Clean prefetch cache",
            "Watch temp folder growth (live)",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            removed = 0
            for name, path in tmp_dirs:
                if os.path.isdir(path):
                    for dp, dns, fns in os.walk(path, topdown=False):
                        for f in fns:
                            try: os.remove(os.path.join(dp, f)); removed += 1
                            except Exception:
                                pass
            console.print(f"  [green]✓ Removed {removed} temp files[/green]")
        elif c == 1:
            path = os.environ.get("TEMP", "")
            removed = 0
            if path and os.path.isdir(path):
                for dp, dns, fns in os.walk(path, topdown=False):
                    for f in fns:
                        try: os.remove(os.path.join(dp, f)); removed += 1
                        except Exception:
                            pass
            console.print(f"  [green]✓ Removed {removed} user temp files[/green]")
        elif c == 2:
            path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")
            removed = 0
            if os.path.isdir(path):
                for dp, dns, fns in os.walk(path, topdown=False):
                    for f in fns:
                        try: os.remove(os.path.join(dp, f)); removed += 1
                        except Exception:
                            pass
            console.print(f"  [green]✓ Removed {removed} Windows temp files[/green]")
        elif c == 3:
            path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Prefetch")
            removed = 0
            if os.path.isdir(path):
                for f in os.listdir(path):
                    try: os.remove(os.path.join(path, f)); removed += 1
                    except Exception:
                        pass
            console.print(f"  [green]✓ Removed {removed} prefetch files[/green]")
        elif c == 4:
            path = os.environ.get("TEMP", "")
            if not path or not os.path.isdir(path):
                console.print("  [red]Temp dir not found[/red]")
                pause(); continue
            console.print(f"  [yellow]Watching {path}... (CTRL+C to stop)[/yellow]\n")
            prev_count = sum(len(fns) for _, _, fns in os.walk(path))
            prev_size = sum(os.path.getsize(os.path.join(dp, f))
                           for dp, _, fns in os.walk(path) for f in fns
                           if os.path.exists(os.path.join(dp, f)))
            try:
                while True:
                    time.sleep(3)
                    count = sum(len(fns) for _, _, fns in os.walk(path))
                    size = sum(os.path.getsize(os.path.join(dp, f))
                              for dp, _, fns in os.walk(path) for f in fns
                              if os.path.exists(os.path.join(dp, f)))
                    dc = count - prev_count
                    ds = size - prev_size
                    if dc != 0 or ds != 0:
                        sign = "+" if ds >= 0 else ""
                        console.print(f"  Files: {count} ({'+' if dc >=0 else ''}{dc})  "
                                      f"Size: {fmt_bytes(size)} ({sign}{fmt_bytes(abs(ds))})")
                    prev_count, prev_size = count, size
            except KeyboardInterrupt:
                console.print(f"\n  [dim]Stopped watching[/dim]")
        pause()


def battery_health_report():
    """Generate Windows battery health report."""
    while True:
        header("Battery Health Report", "Laptop battery diagnostics")
        items = [
            "Generate full battery report (HTML)",
            "Show battery status",
            "Show power efficiency diagnostics",
            "Show estimated battery life",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            path = os.path.join(HOME, "Desktop", "battery-report.html")
            run_cmd(f'powercfg /batteryreport /output "{path}"')
            console.print(f"  [green]✓ Battery report saved to {path}[/green]")
        elif c == 1:
            bat = psutil.sensors_battery()
            if bat:
                t = Table(box=box.ROUNDED, header_style="bold cyan")
                t.add_column("Property", width=24)
                t.add_column("Value", width=30)
                t.add_row("Charge", f"{bat.percent}%")
                t.add_row("Plugged In", "Yes" if bat.power_plugged else "No")
                if bat.secsleft > 0 and bat.secsleft != psutil.POWER_TIME_UNLIMITED:
                    hrs = bat.secsleft // 3600
                    mins = (bat.secsleft % 3600) // 60
                    t.add_row("Time Left", f"{hrs}h {mins}m")
                else:
                    t.add_row("Time Left", "Charging" if bat.power_plugged else "Unknown")
                console.print(t)
            else:
                console.print("  [yellow]No battery detected (desktop PC?)[/yellow]")
        elif c == 2:
            path = os.path.join(HOME, "Desktop", "energy-report.html")
            console.print("  [dim]Running diagnostics (takes ~60 seconds)...[/dim]")
            run_cmd(f'powercfg /energy /output "{path}" /duration 10')
            console.print(f"  [green]✓ Energy report saved to {path}[/green]")
        elif c == 3:
            out = run_ps("powercfg /sleepstudy /duration 7 2>&1")
            console.print(f"\n{out or '  [dim]Sleep study not available[/dim]'}")
        pause()


def network_profile_manager():
    """Switch network profiles between Public/Private."""
    while True:
        header("Network Profile Manager", "Change network category for firewall rules")
        out = run_ps("Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory | Format-Table -AutoSize")
        console.print(f"\n{out}\n")
        items = [
            "Set all connections to Private",
            "Set all connections to Public",
            "Set specific adapter to Private",
            "Set specific adapter to Public",
            "Show detailed connection info",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            run_ps("Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private")
            console.print("  [green]✓ All connections set to Private[/green]")
        elif c == 1:
            run_ps("Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Public")
            console.print("  [green]✓ All connections set to Public[/green]")
        elif c == 2:
            name = ask("Adapter alias (e.g. Wi-Fi, Ethernet)")
            if name:
                run_ps(f"Set-NetConnectionProfile -InterfaceAlias '{name}' -NetworkCategory Private")
                console.print(f"  [green]✓ {name} set to Private[/green]")
        elif c == 3:
            name = ask("Adapter alias")
            if name:
                run_ps(f"Set-NetConnectionProfile -InterfaceAlias '{name}' -NetworkCategory Public")
                console.print(f"  [green]✓ {name} set to Public[/green]")
        elif c == 4:
            out = run_ps("Get-NetConnectionProfile | Format-List *")
            console.print(f"\n{out}")
        pause()


def windows_feature_manager():
    """Enable/disable Windows optional features."""
    while True:
        header("Windows Feature Manager", "Toggle optional Windows features")
        items = [
            "List all optional features",
            "List enabled features only",
            "List disabled features only",
            "Enable a feature",
            "Disable a feature",
            "Quick toggles (common features)",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-WindowsOptionalFeature -Online | Select-Object FeatureName, State | "
                         "Sort-Object State, FeatureName | Format-Table -AutoSize | Out-String -Width 200")
            console.print(f"\n{out[:4000]}")
        elif c == 1:
            out = run_ps("Get-WindowsOptionalFeature -Online | Where-Object State -eq 'Enabled' | "
                         "Select-Object FeatureName | Sort-Object FeatureName | Format-Table -AutoSize")
            console.print(f"\n{out}")
        elif c == 2:
            out = run_ps("Get-WindowsOptionalFeature -Online | Where-Object State -eq 'Disabled' | "
                         "Select-Object FeatureName | Sort-Object FeatureName | Format-Table -AutoSize")
            console.print(f"\n{out[:4000]}")
        elif c == 3:
            name = ask("Feature name to enable")
            if name:
                run_ps(f"Enable-WindowsOptionalFeature -Online -FeatureName '{name}' -NoRestart")
                console.print(f"  [green]✓ {name} enabled[/green]")
        elif c == 4:
            name = ask("Feature name to disable")
            if name:
                run_ps(f"Disable-WindowsOptionalFeature -Online -FeatureName '{name}' -NoRestart")
                console.print(f"  [green]✓ {name} disabled[/green]")
        elif c == 5:
            features = [
                "Windows Subsystem for Linux",
                "Virtual Machine Platform",
                ".NET Framework 3.5",
                "Windows Sandbox",
                "Hyper-V",
                "Telnet Client",
                "TFTP Client",
                "SMB 1.0/CIFS",
            ]
            feature_names = [
                "Microsoft-Windows-Subsystem-Linux",
                "VirtualMachinePlatform",
                "NetFx3",
                "Containers-DisposableClientVM",
                "Microsoft-Hyper-V-All",
                "TelnetClient",
                "TFTP",
                "SMB1Protocol",
            ]
            fc = numbered_menu(features)
            if fc != -1:
                fname = feature_names[fc]
                action = numbered_menu(["Enable", "Disable"])
                if action == 0:
                    run_ps(f"Enable-WindowsOptionalFeature -Online -FeatureName '{fname}' -NoRestart")
                    console.print(f"  [green]✓ {features[fc]} enabled[/green]")
                elif action == 1:
                    run_ps(f"Disable-WindowsOptionalFeature -Online -FeatureName '{fname}' -NoRestart")
                    console.print(f"  [green]✓ {features[fc]} disabled[/green]")
        pause()


def clipboard_manager():
    """View and manage clipboard content."""
    while True:
        header("Clipboard Manager", "View and manage clipboard")
        items = [
            "Show current clipboard text",
            "Show clipboard history (if enabled)",
            "Clear clipboard",
            "Enable clipboard history",
            "Disable clipboard history",
            "Copy file contents to clipboard",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-Clipboard -ErrorAction SilentlyContinue")
            if out:
                console.print(Panel(out[:2000], title="Clipboard Content", style="cyan"))
            else:
                console.print("  [dim]Clipboard is empty or non-text content[/dim]")
        elif c == 1:
            out = run_ps('Get-Clipboard -TextFormatType UnicodeText -ErrorAction SilentlyContinue')
            console.print(f"\n{out or '  [dim]No clipboard history available[/dim]'}")
        elif c == 2:
            run_ps("Set-Clipboard -Value $null")
            console.print("  [green]✓ Clipboard cleared[/green]")
        elif c == 3:
            run_cmd('reg add "HKCU\\Software\\Microsoft\\Clipboard" /v EnableClipboardHistory /t REG_DWORD /d 1 /f')
            console.print("  [green]✓ Clipboard history enabled[/green]")
        elif c == 4:
            run_cmd('reg add "HKCU\\Software\\Microsoft\\Clipboard" /v EnableClipboardHistory /t REG_DWORD /d 0 /f')
            console.print("  [green]✓ Clipboard history disabled[/green]")
        elif c == 5:
            fpath = ask("File path to copy")
            if fpath and os.path.isfile(fpath):
                with open(fpath, "r", errors="replace") as f:
                    content = f.read()[:50000]
                run_ps(f"Set-Clipboard -Value @'\n{content}\n'@")
                console.print(f"  [green]✓ {len(content)} chars copied to clipboard[/green]")
            else:
                console.print("  [red]File not found[/red]")
        pause()


def service_dependency_viewer():
    """View Windows service dependency trees."""
    while True:
        header("Service Dependency Viewer", "Explore service relationships")
        items = [
            "Show all running services with dependencies",
            "Search service by name",
            "Show dependency tree for a service",
            "Show services that depend on a service",
            "Show orphaned services (no dependencies)",
            "Show failed services",
        ]
        c = numbered_menu(items)
        if c == -1: return
        if c == 0:
            out = run_ps("Get-Service | Where-Object Status -eq Running | "
                         "Select-Object Name, DisplayName, @{N='DependsOn';E={($_.ServicesDependedOn.Name -join ', ')}} | "
                         "Where-Object DependsOn | Format-Table -AutoSize | Out-String -Width 200")
            console.print(f"\n{out[:4000]}")
        elif c == 1:
            name = ask("Service name (partial)")
            if name:
                out = run_ps(f"Get-Service *{name}* | Select-Object Name, DisplayName, Status, StartType | Format-Table -AutoSize")
                console.print(f"\n{out or '  [dim]No services found[/dim]'}")
        elif c == 2:
            name = ask("Exact service name")
            if name:
                out = run_ps(f"$svc = Get-Service '{name}' -ErrorAction SilentlyContinue; "
                             f"if ($svc) {{ "
                             f"Write-Host '=== {name} depends on ==='; "
                             f"$svc.ServicesDependedOn | Select-Object Name, Status | Format-Table -AutoSize; "
                             f"Write-Host '=== Services depending on {name} ==='; "
                             f"$svc.DependentServices | Select-Object Name, Status | Format-Table -AutoSize "
                             f"}} else {{ Write-Host 'Service not found' }}")
                console.print(f"\n{out}")
        elif c == 3:
            name = ask("Service name")
            if name:
                out = run_ps(f"(Get-Service '{name}' -ErrorAction SilentlyContinue).DependentServices | "
                             f"Select-Object Name, DisplayName, Status | Format-Table -AutoSize")
                console.print(f"\n{out or '  [dim]No dependent services[/dim]'}")
        elif c == 4:
            out = run_ps("Get-Service | Where-Object { -not $_.ServicesDependedOn -and -not $_.DependentServices } | "
                         "Select-Object Name, DisplayName, Status | Sort-Object Status | "
                         "Format-Table -AutoSize | Out-String -Width 200")
            console.print(f"\n{out[:4000]}")
        elif c == 5:
            out = run_ps("Get-Service | Where-Object Status -ne 'Running' | "
                         "Where-Object StartType -eq 'Automatic' | "
                         "Select-Object Name, DisplayName, Status | Format-Table -AutoSize")
            console.print(f"\n{out or '  [dim]All auto-start services are running[/dim]'}")
        pause()



def file_search_tool():
    """Search for files by name pattern"""
    while True:
        header("File Search", "Find files by name or glob pattern")
        directory = ask("Directory to search (B=back)", str(HOME))
        if directory.lower() in ("b", ""): return
        pattern = ask("Search pattern (e.g. *.txt, report*, *.log)")
        if not pattern: continue

        console.print(f"\n  [yellow]Searching {directory}...[/yellow]\n")
        results = []
        try:
            for f in Path(directory).rglob(pattern):
                results.append(f)
                if len(results) >= 200: break
        except Exception as e:
            console.print(f"  [red]{e}[/red]"); pause(); continue

        if not results:
            console.print("  [dim]No files found.[/dim]"); pause(); continue

        t = Table(box=box.SIMPLE, header_style="bold cyan")
        t.add_column("#", width=5, justify="right")
        t.add_column("Name", width=30)
        t.add_column("Size", width=10, justify="right")
        t.add_column("Modified", width=18)
        t.add_column("Path", width=36, style="dim")
        for i, f in enumerate(results[:50], 1):
            try:
                stat = f.stat()
                t.add_row(str(i), f.name[:29], fmt_bytes(stat.st_size),
                          datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                          str(f.parent)[:35])
            except Exception:
                pass
        console.print(t)
        console.print(f"\n  [cyan]{len(results)} files found{'' if len(results) < 200 else ' (limited to 200)'}[/cyan]")
        pause()



def duplicate_file_finder():
    """Find duplicate files by content hash"""
    while True:
        header("Duplicate File Finder", "Find duplicate files by content")
        directory = ask("Directory to scan (B=back)", str(HOME / "Downloads"))
        if directory.lower() in ("b", ""): return

        min_size = ask("Minimum file size in KB", "1")
        try: min_bytes = int(min_size) * 1024
        except: min_bytes = 1024

        console.print(f"\n  [yellow]Scanning {directory}...[/yellow]")

        size_map = {}
        file_count = 0
        try:
            for f in Path(directory).rglob("*"):
                if f.is_file():
                    try:
                        sz = f.stat().st_size
                        if sz >= min_bytes:
                            size_map.setdefault(sz, []).append(f)
                            file_count += 1
                    except Exception:
                        pass
        except Exception as e:
            console.print(f"  [red]{e}[/red]"); pause(); continue

        candidates = {sz: files for sz, files in size_map.items() if len(files) > 1}
        total_cand = sum(len(f) for f in candidates.values())
        console.print(f"  [dim]Scanned {file_count} files, {total_cand} candidates to hash[/dim]")

        hash_map = {}
        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), console=console) as prog:
            task = prog.add_task("Hashing...", total=total_cand)
            for sz, files in candidates.items():
                for f in files:
                    try:
                        h = hashlib.sha256()
                        with open(f, "rb") as fh:
                            for chunk in iter(lambda: fh.read(65536), b""):
                                h.update(chunk)
                        digest = h.hexdigest()
                        hash_map.setdefault(digest, []).append(f)
                    except Exception:
                        pass
                    prog.advance(task)

        dupes = {h: files for h, files in hash_map.items() if len(files) > 1}

        if not dupes:
            console.print("\n  [green]No duplicates found![/green]"); pause(); continue

        header("Duplicate File Finder", f"{len(dupes)} duplicate groups")
        total_waste = 0
        for gn, (h, files) in enumerate(sorted(dupes.items(),
                key=lambda x: x[1][0].stat().st_size, reverse=True), 1):
            if gn > 20: break
            sz = files[0].stat().st_size
            total_waste += sz * (len(files) - 1)
            console.print(f"\n  [bold yellow]Group {gn}[/bold yellow] — {fmt_bytes(sz)} × {len(files)} copies:")
            for f in files:
                console.print(f"    [dim]{f}[/dim]")
        console.print(f"\n  [bold]Wasted space: [red]{fmt_bytes(total_waste)}[/red][/bold]")
        if len(dupes) > 20:
            console.print(f"  [dim]... and {len(dupes) - 20} more groups[/dim]")
        pause()



def bulk_file_renamer():
    """Rename multiple files at once"""
    while True:
        header("Bulk File Renamer", "Rename multiple files using patterns")
        directory = ask("Directory (B=back)").strip().strip('"')
        if directory.lower() in ("b", ""): return

        if not Path(directory).is_dir():
            console.print("  [red]Not a valid directory.[/red]"); pause(); continue

        files = sorted([f for f in Path(directory).iterdir() if f.is_file()])
        if not files:
            console.print("  [dim]No files in directory.[/dim]"); pause(); continue

        console.print(f"  [dim]{len(files)} files found[/dim]\n")
        for i, f in enumerate(files[:20], 1):
            console.print(f"  {i:3d}. {f.name}")
        if len(files) > 20:
            console.print(f"  [dim]... and {len(files)-20} more[/dim]")

        opts = [
            "Find & Replace in filenames",
            "Add prefix",
            "Add suffix (before extension)",
            "Sequential numbering",
            "Lowercase all filenames",
            "Replace spaces with underscores",
        ]
        sel = numbered_menu("Rename Mode", opts)
        if sel == -1: continue

        previews = []
        if sel == 0:
            find = ask("Find what")
            repl = ask("Replace with")
            for f in files:
                new_name = f.name.replace(find, repl)
                if new_name != f.name:
                    previews.append((f, f.parent / new_name))
        elif sel == 1:
            prefix = ask("Prefix to add")
            for f in files:
                previews.append((f, f.parent / (prefix + f.name)))
        elif sel == 2:
            suffix = ask("Suffix to add")
            for f in files:
                previews.append((f, f.parent / (f.stem + suffix + f.suffix)))
        elif sel == 3:
            start = int(ask("Start number", "1"))
            pad = int(ask("Zero-pad width", "3"))
            for i, f in enumerate(files, start):
                previews.append((f, f.parent / f"{i:0{pad}d}{f.suffix}"))
        elif sel == 4:
            for f in files:
                new_name = f.name.lower()
                if new_name != f.name:
                    previews.append((f, f.parent / new_name))
        elif sel == 5:
            for f in files:
                new_name = f.name.replace(" ", "_")
                if new_name != f.name:
                    previews.append((f, f.parent / new_name))

        if not previews:
            console.print("  [dim]No changes to make.[/dim]"); pause(); continue

        console.print(f"\n  [bold]Preview ({len(previews)} files):[/bold]\n")
        for old, new in previews[:15]:
            console.print(f"  [red]{old.name}[/red] → [green]{new.name}[/green]")
        if len(previews) > 15:
            console.print(f"  [dim]... and {len(previews)-15} more[/dim]")

        if confirm(f"Rename {len(previews)} files?"):
            renamed = 0
            for old, new in previews:
                try:
                    old.rename(new)
                    renamed += 1
                except Exception as e:
                    console.print(f"  [red]Failed: {old.name} — {e}[/red]")
            console.print(f"  [green]Renamed {renamed} files.[/green]")
        pause()



def stopwatch_timer():
    """Stopwatch and countdown timer"""
    while True:
        opts = ["Stopwatch", "Countdown Timer"]
        sel = numbered_menu("Stopwatch & Timer", opts)
        if sel == -1: return

        if sel == 0:
            header("Stopwatch", "Press ENTER to start, ENTER again to stop")
            input("  Press ENTER to start...")
            start = time.time()
            console.print("  [green]Running...[/green] Press ENTER to stop.")
            input()
            elapsed = time.time() - start
            mins, secs = divmod(elapsed, 60)
            hrs, mins = divmod(mins, 60)
            console.print(f"\n  [bold cyan]Elapsed: {int(hrs):02d}:{int(mins):02d}:{secs:05.2f}[/bold cyan]")
            console.print(f"  [dim]({elapsed:.3f} seconds total)[/dim]")
            pause()

        else:
            header("Countdown Timer")
            duration = ask("Duration in seconds (or M:SS)", "60")
            try:
                if ":" in duration:
                    parts = duration.split(":")
                    total = int(parts[0]) * 60 + int(parts[1])
                else:
                    total = int(duration)
            except:
                console.print("  [red]Invalid format.[/red]"); pause(); continue

            console.print(f"  [yellow]Counting down from {total}s... Press ENTER to cancel.[/yellow]\n")
            stop = False
            def _wait():
                nonlocal stop; input(); stop = True
            threading.Thread(target=_wait, daemon=True).start()

            start = time.time()
            while not stop:
                remaining = total - (time.time() - start)
                if remaining <= 0:
                    console.print(f"\r  [bold green]TIME'S UP!  {'='*30}[/bold green]")
                    try:
                        import winsound
                        for _ in range(3): winsound.Beep(1000, 300); time.sleep(0.2)
                    except Exception:
                        pass
                    break
                m, s = divmod(remaining, 60)
                console.print(f"\r  [bold cyan]{int(m):02d}:{s:05.2f}[/bold cyan] remaining...", end="")
                time.sleep(0.1)
            pause()



def quick_calculator():
    """Safe math expression calculator using AST"""
    import ast, operator, math

    OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
    }

    def safe_eval(expr):
        expr = expr.replace("pi", str(math.pi)).replace("tau", str(math.tau))
        tree = ast.parse(expr, mode='eval')
        def _eval(node):
            if isinstance(node, ast.Expression): return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp):
                op = OPS.get(type(node.op))
                if not op: raise ValueError("Unsupported operator")
                return op(_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp):
                op = OPS.get(type(node.op))
                if not op: raise ValueError("Unsupported operator")
                return op(_eval(node.operand))
            raise ValueError("Unsupported expression")
        return _eval(tree)

    header("Quick Calculator", "Type math expressions, B to quit")
    console.print("  [dim]Examples: 2+3, 15*7, 2**10, 100/3, (5+3)*2[/dim]\n")

    while True:
        expr = ask("calc").strip()
        if expr.lower() in ("b", "q", ""): return
        try:
            result = safe_eval(expr)
            if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
                console.print(f"  = [bold green]{int(result)}[/bold green]")
            else:
                console.print(f"  = [bold green]{result}[/bold green]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")



def unit_converter():
    """Convert between common units"""
    while True:
        header("Unit Converter")
        categories = [
            "Bytes (B, KB, MB, GB, TB)",
            "Temperature (C, F, K)",
            "Distance (mm, cm, m, km, in, ft, mi)",
            "Weight (g, kg, oz, lb)",
            "Time (sec, min, hr, day, week, year)",
            "Speed (m/s, km/h, mph, knots)",
        ]
        sel = numbered_menu("Unit Converter", categories)
        if sel == -1: return
        header("Unit Converter", categories[sel])

        try:
            val = float(ask("Value"))
        except:
            console.print("  [red]Not a number.[/red]"); pause(); continue

        if sel == 0:
            units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4, "PB": 1024**5}
            fu = ask("From (B/KB/MB/GB/TB/PB)", "GB").upper()
            if fu not in units: console.print("  [red]Unknown unit[/red]"); pause(); continue
            base = val * units[fu]
            console.print()
            for u, m in units.items():
                col = "cyan" if u == fu else "white"
                console.print(f"  [{col}]{base / m:>18,.4f} {u}[/{col}]")

        elif sel == 1:
            fu = ask("From (C/F/K)", "C").upper()
            if fu == "C": c = val
            elif fu == "F": c = (val - 32) * 5 / 9
            elif fu == "K": c = val - 273.15
            else: console.print("  [red]Unknown unit[/red]"); pause(); continue
            console.print(f"\n  [cyan]{c:.2f} °C[/cyan]")
            console.print(f"  [cyan]{c * 9/5 + 32:.2f} °F[/cyan]")
            console.print(f"  [cyan]{c + 273.15:.2f} K[/cyan]")

        elif sel == 2:
            units = {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000,
                     "in": 0.0254, "ft": 0.3048, "mi": 1609.344}
            fu = ask("From (mm/cm/m/km/in/ft/mi)", "m").lower()
            if fu not in units: console.print("  [red]Unknown unit[/red]"); pause(); continue
            base = val * units[fu]
            console.print()
            for u, m in units.items():
                col = "cyan" if u == fu else "white"
                console.print(f"  [{col}]{base / m:>14,.4f} {u}[/{col}]")

        elif sel == 3:
            units = {"mg": 0.001, "g": 1, "kg": 1000, "oz": 28.3495, "lb": 453.592}
            fu = ask("From (mg/g/kg/oz/lb)", "kg").lower()
            if fu not in units: console.print("  [red]Unknown unit[/red]"); pause(); continue
            base = val * units[fu]
            console.print()
            for u, m in units.items():
                col = "cyan" if u == fu else "white"
                console.print(f"  [{col}]{base / m:>14,.4f} {u}[/{col}]")

        elif sel == 4:
            units = {"sec": 1, "min": 60, "hr": 3600, "day": 86400, "week": 604800, "year": 31557600}
            fu = ask("From (sec/min/hr/day/week/year)", "hr").lower()
            if fu not in units: console.print("  [red]Unknown unit[/red]"); pause(); continue
            base = val * units[fu]
            console.print()
            for u, m in units.items():
                col = "cyan" if u == fu else "white"
                console.print(f"  [{col}]{base / m:>16,.4f} {u}[/{col}]")

        elif sel == 5:
            units = {"m/s": 1, "km/h": 1/3.6, "mph": 0.44704, "knots": 0.514444}
            fu = ask("From (m/s, km/h, mph, knots)", "km/h").lower()
            if fu not in units: console.print("  [red]Unknown unit[/red]"); pause(); continue
            base = val * units[fu]
            console.print()
            for u, m in units.items():
                col = "cyan" if u == fu else "white"
                console.print(f"  [{col}]{base / m:>12,.4f} {u}[/{col}]")

        pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY & DESCRIPTIONS (powers search, favorites, verbose menus)
# ═══════════════════════════════════════════════════════════════════════════════
TOOL_DESCRIPTIONS = {
    # Tools tab
    "Junk File Cleaner":        "Clean temp files, caches, crash dumps to free disk space",
    "Process Manager":          "View, sort and kill running processes by CPU/RAM",
    "Startup Manager":          "Manage programs that run at Windows startup",
    "Network Tools":            "IP info, ping, DNS benchmark, Wi-Fi passwords",
    "Background Services":      "Stop bloatware services to free system resources",
    "Registry Cleaner":         "Scan and fix broken/orphaned registry entries",
    "Disk Optimizer":           "Defragment HDDs, TRIM SSDs, analyze disk usage",
    "System Repair":            "Run SFC, DISM, and other repair commands",
    "Event Log Viewer":         "Browse and search Windows event logs",
    "Environment Variables":    "View and edit system/user environment variables",
    "Firewall & Open Ports":    "Check firewall rules and listening ports",
    "Hash Checker & Passwords": "Check file hashes and generate secure passwords",
    "System Information":       "Detailed system specs: CPU, RAM, GPU, drives",
    "Live Performance Monitor": "Real-time CPU, RAM, disk, network monitoring",
    "Memory Optimizer":         "Free cached RAM and manage virtual memory",
    "Scheduled Tasks":          "View and manage Windows scheduled tasks",
    "Hosts File Editor":        "Edit the hosts file to block/redirect domains",
    "WiFi Manager":             "View saved Wi-Fi networks and passwords",
    "Installed Programs":       "List all installed programs with size info",
    "Disk Space Analyzer":      "Find what's using your disk space",
    "System Restore Manager":   "Create and manage system restore points",
    "Certificate Manager":      "View installed SSL/TLS certificates",
    "Temp File Monitor":        "Monitor temp folder growth in real-time",
    "Battery Health Report":    "Generate detailed battery health report",
    "Network Profile Manager":  "Manage network profiles (public/private)",
    "Windows Feature Manager":  "Enable/disable Windows optional features",
    "Clipboard Manager":        "View and manage clipboard history",
    "Service Dependencies":     "View service dependency tree",
    # Optimize tab
    "Full Optimize  ":          "One-click apply all recommended optimizations",
    "Power Plan Manager":       "Switch between power plans, install Ultimate Performance",
    "Game & Performance":       "Game Mode, GPU scheduling, mouse accel tweaks",
    "Visual Effects":           "Disable animations for snappier Windows",
    "CPU Priority Tweaks":      "Core parking, priority, scheduling tweaks",
    "GPU Optimization":         "HAGS, preemption, TDR delay tweaks",
    "SSD / HDD Tweaks":        "TRIM, write caching, indexing optimizations",
    "Network Latency  (Gaming)":"Nagle, TCP tweaks for lower latency",
    "Telemetry & Privacy":      "Disable Windows data collection and telemetry",
    "Hibernation & Sleep":      "Configure hibernate, sleep, fast startup",
    "Advanced Registry Tweaks": "Power-user registry optimizations",
    "Boot & Startup Analysis":  "Analyze boot time and startup impact",
    "Driver Health Check":      "Check for problematic or outdated drivers",
    "Windows Defender Tuning":  "Optimize Defender without disabling security",
    "Context Menu Cleanup":     "Remove clutter from right-click menus",
    "DNS Optimizer":            "Set fastest DNS servers automatically",
    "RAM Optimizer":             "Advanced RAM management and cleanup",
    "Windows Update Manager":   "Manage Windows Update settings and history",
    "Background Process Killer":"Kill unnecessary background processes",
    "Notification Disabler":    "Disable annoying Windows notifications",
    "Page File Optimizer":      "Optimize virtual memory / page file size",
    "System Timer Resolution":  "Set high-resolution timer for gaming",
    "USB Power Management":     "Disable USB selective suspend",
    "Audio Latency Tweaks":     "Reduce audio latency for gaming/production",
    "Windows Search Optimizer": "Optimize or disable Windows Search indexing",
    "Shader Cache Manager":     "Manage DirectX shader cache for GPU perf",
    "Interrupt Affinity (MSI)": "Optimize interrupt routing (MSI mode)",
    "Boot Config (BCDEdit)":    "Advanced boot configuration tweaks",
    # OSINT tab
    "IP / Domain Lookup":       "Geolocation, ISP, ASN info for any IP/domain",
    "DNS Record Lookup":        "Query A, MX, NS, TXT, CNAME records",
    "Reverse IP Lookup":        "Find domains hosted on the same IP",
    "WHOIS & Domain Intel":     "WHOIS registration data and domain age",
    "Subdomain Finder":         "Discover subdomains using multiple methods",
    "Port Scanner":             "Scan ports with banner grabbing",
    "Breach / Leak Checker":    "Check if email/password appeared in breaches",
    "Google Dorking Helper":    "Generate advanced Google search queries",
    "URL Analyzer":             "Analyze and decode URLs, check redirects",
    "MAC Address Lookup":       "Lookup manufacturer from MAC address",
    "Tor/VPN/Proxy Detector":   "Check if an IP is a Tor exit/VPN/proxy",
    "Website Fingerprinter":    "Detect web server, CMS, frameworks",
    "Email Header Analyzer":    "Parse and trace email headers",
    "EXIF / Image Metadata":    "Extract metadata from image files",
    "Phone Number Lookup":      "Lookup carrier and location for phone numbers",
    "SSL Certificate Checker":  "Inspect SSL cert details and expiry",
    "Geolocation Tracker":      "Track approximate location from IP/phone",
    "Shodan Search Helper":     "Search Shodan for exposed devices",
    "IP Reputation Checker":    "Check if IP is blacklisted/malicious",
    "Username Search":          "Find accounts across 37+ platforms",
    "Social Media Deep Scraper":"Extract public info from social profiles",
    "Dark Web Mention Checker": "Search for mentions on dark web",
    "HTTP Header Analyzer":     "Inspect HTTP response headers",
    "Technology Detector":      "Detect technologies used by a website",
    "Robots & Sitemap Viewer":  "View robots.txt and sitemap.xml",
    "Wayback Machine Checker":  "Check archived versions of a website",
    "Link Extractor":           "Extract all links from a webpage",
    # Utilities tab
    "Text Utilities":           "Case conversion, word count, encoding tools",
    "JSON Formatter":           "Format, validate, and minify JSON",
    "Password Generator":       "Generate secure passwords with custom rules",
    "Hash Generator":           "Generate MD5, SHA1, SHA256 hashes",
    "Base Converter":           "Convert between decimal, hex, binary, octal",
    "Timestamp Converter":      "Convert between Unix timestamps and dates",
    "Quick Calculator":         "Evaluate math expressions",
    "Unit Converter":           "Convert weight, temp, length, data and more",
    "File Search":              "Search for files by name pattern",
    "Duplicate File Finder":    "Find duplicate files by content hash",
    "Bulk File Renamer":        "Batch rename files with patterns",
    "Stopwatch & Timer":        "Stopwatch and countdown timer",
    "Color Picker / Converter": "Convert between HEX, RGB, HSL colors",
    "Diff Tool":                "Compare two text inputs side by side",
    "Port Manager":             "View and kill processes on specific ports",
    "File Watcher":             "Monitor a directory for file changes",
    # New tools descriptions
    "Cert Transparency Search": "Find subdomains via certificate transparency logs (crt.sh)",
    "ASN Lookup":               "Look up Autonomous System Number for an IP/org",
    "Domain Age Checker":       "Check when a domain was registered and its age",
    "Header Security Analyzer": "Check HTTP headers for security best practices",
    "CVE Lookup":               "Search for known vulnerabilities by keyword",
    "JWT Decoder":              "Decode and analyze JSON Web Tokens",
    "Reverse Image Search":     "Generate reverse image search URLs",
    "Favicon Hash Lookup":      "Generate Shodan favicon hash for recon",
    "Hash Cracker":             "Dictionary attack on MD5/SHA1/SHA256 hashes",
    "Directory Bruteforcer":    "Enumerate web directories with wordlists",
    "Subdomain Takeover Check": "Check for dangling CNAME records",
    "Privacy Audit":            "Scan Windows for privacy-invasive settings",
    "Tracker Blocker":          "Block known trackers via hosts file",
    "Browser Data Cleaner":     "Clear cookies, cache, history for all browsers",
    "DNS Leak Test":            "Check if DNS leaks outside your VPN",
    "VPN Connection Checker":   "Verify VPN is active and check for leaks",
    "Webcam / Mic Monitor":     "Check which apps can access camera/mic",
    "Regex Tester":             "Interactive regex testing with highlights",
    "API Tester":               "Send HTTP requests with custom headers/body",
    "Git Dashboard":            "View repo status, commits, branches",
    "Code Line Counter":        "Count lines of code by language",
    "Env Variable Manager":     "View, add, edit environment variables",
    "Cron Expression Builder":  "Build and explain cron/task expressions",
    "File Encryptor":           "AES-256 encrypt/decrypt files with password",
    "Secure File Shredder":     "Securely delete files with overwrite",
    "Archive Manager":          "Create and extract ZIP/TAR archives",
    "File Integrity Checker":   "Generate and verify file checksums",
    "Bandwidth Monitor":        "Real-time upload/download speed display",
    "Network Mapper":           "Discover devices on local network",
    "Visual Traceroute":        "Traceroute with hop latency display",
    "Ping Sweep":               "Ping a range of IPs to find live hosts",
    "Wake-on-LAN":              "Send WOL packets to wake network devices",
    "Connection Monitor":       "Live view of all connections with processes",
    "Windows Debloater v2":     "Remove bloatware apps with per-app toggles",
    "SSD/HDD Health":           "S.M.A.R.T. data and drive health info",
    "Startup Impact Analyzer":  "Show boot time impact per startup item",
    "Memory Leak Detector":     "Find processes with growing memory usage",
    "Windows Hardening":        "Apply security hardening best practices",
    "ASCII Art Generator":      "Convert text to large ASCII art",
    "Matrix Rain":              "The Matrix digital rain animation",
    "System Stats Flex":        "Neofetch-style system info display",
    "Typing Speed Test":        "Test your typing speed (WPM)",
    "Number Guessing Game":     "Guess the number with difficulty levels",
    "Rock Paper Scissors":      "Play RPS against the computer",
    "Settings":                 "Configure API keys, preferences, manage config",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  SEARCH FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════
def search_tools_menu():
    """Search across all tools by name or description."""
    while True:
        header("Tool Search", "Type to search across all tools")
        query = ask("Search (or B to go back)").strip().lower()
        if query in ("b", "q", ""):
            return None

        results = []
        for tab_key, tab_data in TABS.items():
            for idx, (name, func) in enumerate(tab_data["items"]):
                desc = TOOL_DESCRIPTIONS.get(name, "")
                if query in name.lower() or query in desc.lower():
                    results.append((name, func, tab_data["label"], tab_data["color"], desc))

        if not results:
            console.print(f"  [dim]No tools matching '{query}'[/dim]")
            pause()
            continue

        header("Search Results", f"'{query}' — {len(results)} matches")
        for i, (name, func, tab_label, col, desc) in enumerate(results, 1):
            star = "[yellow]★[/yellow] " if is_favorite(name) else ""
            console.print(f"  [bold {col}]{i:>2}[/bold {col}]  {star}{name}  [dim]({tab_label})[/dim]")
            if desc:
                console.print(f"      [dim]{desc}[/dim]")
        console.print(f"  [bold cyan] 0[/bold cyan]  [dim]Back[/dim]\n")

        raw = ask("Pick").strip()
        if raw in ("0", "b", ""):
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(results):
            name, func, _, _, _ = results[int(raw) - 1]
            add_recent(name)
            try:
                func()
            except KeyboardInterrupt:
                pass
            except Exception as e:
                console.print(f"\n  [red]Error: {e}[/red]")
                pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS MENU
# ═══════════════════════════════════════════════════════════════════════════════
def settings_menu():
    while True:
        header("Settings", "Configure your toolkit")
        opts = [
            "API Keys",
            "Toggle Verbose Menus  (show tool descriptions)",
            "Manage Favorites",
            "Clear Recent History",
            "Reset All Settings",
            "View Config File Location",
        ]
        sel = numbered_menu(opts)
        if sel == -1:
            return

        if sel == 0:
            header("API Keys", "Set API keys for OSINT tools")
            console.print(f"  [dim]Current Shodan key: {'***' + CONFIG['api_keys']['shodan'][-4:] if CONFIG['api_keys']['shodan'] else '[not set]'}[/dim]")
            console.print(f"  [dim]Current HIBP key:   {'***' + CONFIG['api_keys']['hibp'][-4:] if CONFIG['api_keys']['hibp'] else '[not set]'}[/dim]\n")
            key_opts = ["Set Shodan API Key", "Set HaveIBeenPwned API Key", "Clear All Keys"]
            sel2 = numbered_menu(key_opts)
            if sel2 == 0:
                val = ask("Shodan API Key").strip()
                if val:
                    CONFIG["api_keys"]["shodan"] = val
                    save_config(CONFIG)
                    console.print("  [green]Saved.[/green]"); time.sleep(0.5)
            elif sel2 == 1:
                val = ask("HIBP API Key").strip()
                if val:
                    CONFIG["api_keys"]["hibp"] = val
                    save_config(CONFIG)
                    console.print("  [green]Saved.[/green]"); time.sleep(0.5)
            elif sel2 == 2:
                CONFIG["api_keys"] = {"shodan": "", "hibp": ""}
                save_config(CONFIG)
                console.print("  [green]Cleared.[/green]"); time.sleep(0.5)

        elif sel == 1:
            CONFIG["verbose_menus"] = not CONFIG.get("verbose_menus", False)
            save_config(CONFIG)
            state = "ON" if CONFIG["verbose_menus"] else "OFF"
            console.print(f"  [green]Verbose menus: {state}[/green]"); time.sleep(0.5)

        elif sel == 2:
            header("Favorites")
            favs = CONFIG.get("favorites", [])
            if not favs:
                console.print("  [dim]No favorites yet. Press F+number in the main menu to add tools.[/dim]")
            else:
                for i, f in enumerate(favs, 1):
                    console.print(f"  [yellow]{i}[/yellow]  [yellow]★[/yellow] {f}")
                console.print(f"\n  [dim]Enter number to remove, C to clear all, B to go back[/dim]")
                raw = ask("").strip().lower()
                if raw == "c":
                    CONFIG["favorites"] = []
                    save_config(CONFIG)
                    console.print("  [green]Cleared.[/green]")
                elif raw.isdigit():
                    idx = int(raw) - 1
                    if 0 <= idx < len(favs):
                        removed = favs.pop(idx)
                        save_config(CONFIG)
                        console.print(f"  [green]Removed {removed}.[/green]")
                time.sleep(0.5)
            pause()

        elif sel == 3:
            CONFIG["recent"] = []
            save_config(CONFIG)
            console.print("  [green]Recent history cleared.[/green]"); pause()

        elif sel == 4:
            if confirm("Reset ALL settings to defaults?"):
                for k, v in DEFAULT_CONFIG.items():
                    CONFIG[k] = v if not isinstance(v, (list, dict)) else (v.copy() if isinstance(v, list) else {**v})
                save_config(CONFIG)
                console.print("  [green]Settings reset.[/green]"); pause()

        elif sel == 5:
            console.print(f"\n  Config file: [cyan]{CONFIG_FILE}[/cyan]")
            console.print(f"  Config dir:  [cyan]{CONFIG_DIR}[/cyan]")
            console.print(f"  Exists:      {'[green]Yes[/green]' if CONFIG_FILE.exists() else '[red]No[/red]'}")
            pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  NEW OSINT TOOLS
# ═══════════════════════════════════════════════════════════════════════════════
def cert_transparency_search():
    while True:
        header("Certificate Transparency Search", "Find subdomains via crt.sh")
        domain = ask("Domain (or B to go back)").strip()
        if domain.lower() in ("b", ""):
            return
        if not validate_domain(domain):
            console.print("  [red]Invalid domain format.[/red]"); pause(); continue

        console.print(f"\n  [yellow]Searching crt.sh for {domain}...[/yellow]\n")
        data = http_json(f"https://crt.sh/?q=%.{urllib.parse.quote(domain)}&output=json", timeout=15)
        if not data:
            console.print("  [red]No results or crt.sh is down.[/red]"); pause(); continue

        subdomains = set()
        for entry in data:
            name = entry.get("name_value", "")
            for line in name.split("\n"):
                line = line.strip().lower()
                if line and "*" not in line:
                    subdomains.add(line)

        t = Table(box=box.ROUNDED, header_style="bold magenta")
        t.add_column("#", width=5)
        t.add_column("Subdomain", width=50)
        t.add_column("First Seen", width=20, style="dim")
        seen = set()
        for i, sub in enumerate(sorted(subdomains), 1):
            if sub not in seen:
                seen.add(sub)
                issuer_date = ""
                for entry in data:
                    if sub in entry.get("name_value", "").lower():
                        issuer_date = entry.get("not_before", "")[:10]
                        break
                t.add_row(str(i), f"[cyan]{sub}[/cyan]", issuer_date)
                if i >= 100: break
        console.print(t)
        console.print(f"\n  [green]Found {len(subdomains)} unique subdomains.[/green]")
        pause()


def asn_lookup():
    while True:
        header("ASN Lookup", "Look up Autonomous System Number info")
        target = ask("IP or ASN (e.g. AS13335) (or B to go back)").strip()
        if target.lower() in ("b", ""):
            return

        console.print(f"\n  [yellow]Looking up {target}...[/yellow]\n")

        if target.upper().startswith("AS"):
            asn_num = target.upper().replace("AS", "")
            data = http_json(f"https://api.bgpview.io/asn/{urllib.parse.quote(asn_num)}")
        else:
            data = http_json(f"https://api.bgpview.io/ip/{urllib.parse.quote(target)}")

        if not data or data.get("status") == "error":
            console.print("  [red]Lookup failed or no data found.[/red]"); pause(); continue

        info = data.get("data", {})
        t = Table(box=box.ROUNDED, header_style="bold magenta", show_header=False)
        t.add_column("Key", style="bold cyan", width=20)
        t.add_column("Value", width=50)

        if "asn" in info:
            t.add_row("ASN", f"AS{info.get('asn', '?')}")
            t.add_row("Name", info.get("name", "?"))
            t.add_row("Description", info.get("description_short", "?"))
            t.add_row("Country", info.get("country_code", "?"))
            t.add_row("Website", info.get("website", "?"))
            t.add_row("Email", info.get("email_contacts", ["?"])[0] if info.get("email_contacts") else "?")
            t.add_row("Traffic Est.", info.get("traffic_estimation", "?"))
        elif "prefixes" in info:
            for prefix in info.get("prefixes", [])[:5]:
                asn_info = prefix.get("asn", {})
                t.add_row("IP", prefix.get("ip", target))
                t.add_row("Prefix", prefix.get("prefix", "?"))
                t.add_row("ASN", f"AS{asn_info.get('asn', '?')}")
                t.add_row("ASN Name", asn_info.get("name", "?"))
                t.add_row("Description", asn_info.get("description", "?"))
                t.add_row("Country", asn_info.get("country_code", "?"))
        else:
            for k, v in list(info.items())[:10]:
                t.add_row(str(k), str(v)[:50])

        console.print(t)
        pause()


def domain_age_checker():
    while True:
        header("Domain Age Checker", "Check registration age of a domain")
        domain = ask("Domain (or B to go back)").strip()
        if domain.lower() in ("b", ""):
            return
        if not validate_domain(domain):
            console.print("  [red]Invalid domain format.[/red]"); pause(); continue

        console.print(f"\n  [yellow]Checking {domain}...[/yellow]\n")
        data = http_json(f"https://api.bgpview.io/search?query_term={urllib.parse.quote(domain)}")

        out = run_ps(f"(Resolve-DnsName -Name {domain} -Type SOA -ErrorAction SilentlyContinue | Select-Object -First 1).PrimaryServer")
        whois_data = http_get(f"https://www.whois.com/whois/{urllib.parse.quote(domain)}", timeout=10)
        creation_date = "Unknown"
        expiry_date = "Unknown"
        registrar = "Unknown"
        if whois_data:
            for line in whois_data.split("\n"):
                ll = line.lower()
                if "creation date" in ll or "created on" in ll or "registration date" in ll:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        creation_date = parts[1].strip()[:20]
                if "expir" in ll and "date" in ll:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        expiry_date = parts[1].strip()[:20]
                if "registrar" in ll and registrar == "Unknown":
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        registrar = parts[1].strip()[:40]

        age_str = "Unknown"
        try:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%b-%Y"):
                try:
                    created = datetime.strptime(creation_date[:19], fmt)
                    delta = datetime.now() - created
                    years = delta.days // 365
                    months = (delta.days % 365) // 30
                    age_str = f"{years} years, {months} months ({delta.days} days)"
                    break
                except ValueError:
                    continue
        except Exception:
            pass

        t = Table(box=box.ROUNDED, header_style="bold magenta", show_header=False)
        t.add_column("Key", style="bold cyan", width=18)
        t.add_column("Value", width=45)
        t.add_row("Domain", f"[cyan]{domain}[/cyan]")
        t.add_row("Created", creation_date)
        t.add_row("Expires", expiry_date)
        t.add_row("Age", f"[green]{age_str}[/green]")
        t.add_row("Registrar", registrar)
        t.add_row("Primary NS", out if out else "?")
        console.print(t)
        pause()


def reverse_image_search():
    while True:
        header("Reverse Image Search", "Generate search URLs for an image")
        url = ask("Image URL (or B to go back)").strip()
        if url.lower() in ("b", ""):
            return

        encoded = urllib.parse.quote(url, safe='')
        console.print(f"\n  [bold cyan]Reverse Image Search Links:[/bold cyan]\n")
        links = [
            ("Google Images", f"https://lens.google.com/uploadbyurl?url={encoded}"),
            ("Yandex Images", f"https://yandex.com/images/search?rpt=imageview&url={encoded}"),
            ("Bing Visual", f"https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&sbisrc=UrlPaste&q=imgurl:{encoded}"),
            ("TinEye", f"https://tineye.com/search?url={encoded}"),
        ]
        for name, link in links:
            console.print(f"  [yellow]{name}:[/yellow]")
            console.print(f"  [dim]{link}[/dim]\n")
        pause()


def favicon_hash_lookup():
    while True:
        header("Favicon Hash Lookup", "Generate MMH3 hash for Shodan favicon search")
        url = ask("Website URL (e.g. https://example.com) (or B)").strip()
        if url.lower() in ("b", ""):
            return
        if not url.startswith("http"):
            url = "https://" + url

        favicon_url = url.rstrip("/") + "/favicon.ico"
        console.print(f"\n  [yellow]Fetching {favicon_url}...[/yellow]\n")

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(favicon_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                favicon_data = r.read()

            import codecs
            b64 = codecs.encode(favicon_data, "base64")
            # Simple mmh3-like hash for Shodan
            h = hashlib.md5(b64).hexdigest()
            console.print(f"  Favicon size:  [cyan]{len(favicon_data)} bytes[/cyan]")
            console.print(f"  MD5 hash:      [cyan]{hashlib.md5(favicon_data).hexdigest()}[/cyan]")
            console.print(f"  Base64 MD5:    [cyan]{h}[/cyan]")
            console.print(f"\n  [yellow]Shodan query:[/yellow]")
            console.print(f"  [dim]http.favicon.hash:{h}[/dim]")
            console.print(f"\n  [dim]Note: For proper mmh3 hash, install mmh3: pip install mmh3[/dim]")
        except Exception as e:
            console.print(f"  [red]Failed to fetch favicon: {e}[/red]")
        pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  SECURITY / PENTEST TOOLS
# ═══════════════════════════════════════════════════════════════════════════════
def hash_cracker():
    while True:
        header("Hash Cracker", "Dictionary attack on common hashes")
        target_hash = ask("Hash to crack (or B to go back)").strip()
        if target_hash.lower() in ("b", ""):
            return

        hash_len = len(target_hash)
        if hash_len == 32:
            algo = "md5"
        elif hash_len == 40:
            algo = "sha1"
        elif hash_len == 64:
            algo = "sha256"
        else:
            console.print("  [red]Unknown hash type. Supported: MD5 (32), SHA1 (40), SHA256 (64).[/red]")
            pause(); continue

        console.print(f"  [dim]Detected: {algo.upper()} ({hash_len} chars)[/dim]\n")

        opts = ["Common passwords (built-in ~1000)", "Custom wordlist file"]
        sel = numbered_menu(opts)
        if sel == -1:
            continue

        words = []
        if sel == 0:
            common = [
                "password", "123456", "12345678", "qwerty", "abc123", "monkey", "1234567",
                "letmein", "trustno1", "dragon", "baseball", "iloveyou", "master", "sunshine",
                "ashley", "bailey", "shadow", "123123", "654321", "superman", "qazwsx",
                "michael", "football", "password1", "password123", "batman", "login",
                "admin", "admin123", "root", "toor", "pass", "test", "guest", "master",
                "changeme", "hello", "charlie", "donald", "princess", "welcome", "linux",
            ]
            # Generate variations
            for w in list(common):
                common.extend([w.upper(), w.capitalize(), w + "1", w + "123", w + "!", w + "2024", w + "2025", w + "2026"])
            words = list(set(common))
        else:
            path = ask("Wordlist file path").strip()
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    words = [line.strip() for line in f if line.strip()]
            except OSError as e:
                console.print(f"  [red]{e}[/red]"); pause(); continue

        console.print(f"  [yellow]Trying {len(words)} passwords...[/yellow]\n")
        found = False
        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
            task = prog.add_task("Cracking...", total=len(words))
            for word in words:
                h = hashlib.new(algo, word.encode()).hexdigest()
                if h == target_hash.lower():
                    prog.stop()
                    console.print(f"\n  [bold green]CRACKED![/bold green]")
                    console.print(f"  Password: [bold yellow]{word}[/bold yellow]")
                    console.print(f"  Hash:     [dim]{target_hash}[/dim]")
                    found = True
                    break
                prog.advance(task)

        if not found:
            console.print(f"\n  [red]Not found in wordlist ({len(words)} attempts).[/red]")
        pause()


def directory_bruteforcer():
    while True:
        header("Directory Bruteforcer", "Enumerate web directories")
        url = ask("Target URL (e.g. https://example.com) (or B)").strip()
        if url.lower() in ("b", ""):
            return
        if not url.startswith("http"):
            url = "https://" + url
        url = url.rstrip("/")

        common_dirs = [
            "admin", "login", "wp-admin", "wp-login.php", "wp-content", "wp-includes",
            "api", "api/v1", "api/v2", "docs", "swagger", "graphql",
            "admin/login", "dashboard", "panel", "cpanel", "phpmyadmin",
            ".git", ".git/config", ".env", ".htaccess", "robots.txt", "sitemap.xml",
            "backup", "backups", "db", "database", "dump", "sql",
            "config", "conf", "configuration", "settings", "setup",
            "uploads", "upload", "files", "media", "images", "assets", "static",
            "test", "testing", "debug", "dev", "staging", "beta",
            "server-status", "server-info", ".well-known", "info.php", "phpinfo.php",
            "console", "shell", "cmd", "terminal", "manage",
            "user", "users", "account", "accounts", "profile", "register",
            "cgi-bin", "bin", "scripts", "includes", "lib",
            "tmp", "temp", "cache", "logs", "log",
        ]

        console.print(f"  [yellow]Scanning {len(common_dirs)} paths on {url}...[/yellow]\n")
        found = []
        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
            task = prog.add_task("Scanning...", total=len(common_dirs))
            for d in common_dirs:
                prog.update(task, description=f"/{d}")
                try:
                    test_url = f"{url}/{d}"
                    req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
                    ctx = ssl.create_default_context()
                    with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                        code = r.getcode()
                        size = r.headers.get("Content-Length", "?")
                        if code < 400:
                            found.append((d, code, size))
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403):
                        found.append((d, e.code, "restricted"))
                except Exception:
                    pass
                prog.advance(task)

        if found:
            t = Table(box=box.ROUNDED, header_style="bold magenta")
            t.add_column("Path", width=35)
            t.add_column("Status", width=10)
            t.add_column("Size", width=12)
            for path, code, size in found:
                col = "green" if code == 200 else "yellow" if code in (301, 302) else "red"
                t.add_row(f"/{path}", f"[{col}]{code}[/{col}]", str(size))
            console.print(t)
            console.print(f"\n  [green]Found {len(found)} accessible paths.[/green]")
        else:
            console.print("  [dim]No paths found.[/dim]")
        pause()


def subdomain_takeover_check():
    while True:
        header("Subdomain Takeover Checker", "Check for dangling CNAME records")
        domain = ask("Domain to check (or B)").strip()
        if domain.lower() in ("b", ""):
            return
        if not validate_domain(domain):
            console.print("  [red]Invalid domain.[/red]"); pause(); continue

        console.print(f"\n  [yellow]Finding subdomains...[/yellow]")
        data = http_json(f"https://crt.sh/?q=%.{urllib.parse.quote(domain)}&output=json", timeout=15)
        if not data:
            console.print("  [red]Could not fetch subdomains.[/red]"); pause(); continue

        subdomains = set()
        for entry in data:
            for line in entry.get("name_value", "").split("\n"):
                line = line.strip().lower()
                if line and "*" not in line:
                    subdomains.add(line)

        vulnerable_providers = {
            "amazonaws.com": "AWS S3",
            "azurewebsites.net": "Azure",
            "cloudfront.net": "CloudFront",
            "herokuapp.com": "Heroku",
            "github.io": "GitHub Pages",
            "shopify.com": "Shopify",
            "surge.sh": "Surge",
            "bitbucket.io": "Bitbucket",
            "ghost.io": "Ghost",
            "pantheon.io": "Pantheon",
            "zendesk.com": "Zendesk",
            "readme.io": "ReadMe",
        }

        console.print(f"  [yellow]Checking {len(subdomains)} subdomains for CNAME issues...[/yellow]\n")
        findings = []
        for sub in sorted(subdomains)[:50]:
            try:
                cname_out = run_ps(f"(Resolve-DnsName -Name {sub} -Type CNAME -ErrorAction SilentlyContinue).NameHost")
                if cname_out:
                    for provider_domain, provider_name in vulnerable_providers.items():
                        if provider_domain in cname_out.lower():
                            try:
                                socket.gethostbyname(sub)
                            except socket.gaierror:
                                findings.append((sub, cname_out, provider_name, "VULNERABLE"))
                                break
                            else:
                                findings.append((sub, cname_out, provider_name, "active"))
                                break
            except Exception:
                pass

        if findings:
            t = Table(box=box.ROUNDED, header_style="bold magenta")
            t.add_column("Subdomain", width=30)
            t.add_column("CNAME", width=30)
            t.add_column("Provider", width=12)
            t.add_column("Status", width=12)
            for sub, cname, prov, status in findings:
                col = "red bold" if status == "VULNERABLE" else "green"
                t.add_row(sub, cname, prov, f"[{col}]{status}[/{col}]")
            console.print(t)
        else:
            console.print("  [green]No takeover candidates found.[/green]")
        pause()


def header_security_analyzer():
    while True:
        header("Header Security Analyzer", "Check for missing security headers")
        url = ask("URL to check (or B)").strip()
        if url.lower() in ("b", ""):
            return
        if not url.startswith("http"):
            url = "https://" + url

        console.print(f"\n  [yellow]Checking {url}...[/yellow]\n")
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                headers = dict(r.headers)
        except Exception as e:
            console.print(f"  [red]Failed: {e}[/red]"); pause(); continue

        security_headers = {
            "Strict-Transport-Security": ("HSTS — forces HTTPS", "critical"),
            "Content-Security-Policy": ("CSP — prevents XSS", "critical"),
            "X-Content-Type-Options": ("Prevents MIME sniffing", "high"),
            "X-Frame-Options": ("Prevents clickjacking", "high"),
            "X-XSS-Protection": ("XSS filter (legacy)", "medium"),
            "Referrer-Policy": ("Controls referrer info", "medium"),
            "Permissions-Policy": ("Controls browser features", "medium"),
            "X-Permitted-Cross-Domain-Policies": ("Flash/PDF policy", "low"),
            "Cross-Origin-Embedder-Policy": ("COEP — isolation", "low"),
            "Cross-Origin-Opener-Policy": ("COOP — isolation", "low"),
            "Cross-Origin-Resource-Policy": ("CORP — isolation", "low"),
        }

        t = Table(box=box.ROUNDED, header_style="bold magenta")
        t.add_column("Header", width=35)
        t.add_column("Status", width=10)
        t.add_column("Value / Info", width=35)
        present = 0
        for h_name, (desc, severity) in security_headers.items():
            val = None
            for k, v in headers.items():
                if k.lower() == h_name.lower():
                    val = v
                    break
            if val:
                t.add_row(h_name, "[green]Present[/green]", f"[dim]{val[:34]}[/dim]")
                present += 1
            else:
                sev_col = "red" if severity == "critical" else "yellow" if severity == "high" else "dim"
                t.add_row(h_name, f"[{sev_col}]MISSING[/{sev_col}]", f"[dim]{desc}[/dim]")

        console.print(t)
        score = int(present / len(security_headers) * 100)
        col = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        console.print(f"\n  Security Score: [{col}]{score}%[/{col}] ({present}/{len(security_headers)} headers present)")
        pause()


def cve_lookup():
    while True:
        header("CVE Lookup", "Search for known vulnerabilities")
        query = ask("Search (product, CVE-ID, or keyword) (or B)").strip()
        if query.lower() in ("b", ""):
            return

        console.print(f"\n  [yellow]Searching NVD for '{query}'...[/yellow]\n")

        if query.upper().startswith("CVE-"):
            data = http_json(f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={urllib.parse.quote(query.upper())}", timeout=15)
        else:
            data = http_json(f"https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={urllib.parse.quote(query)}&resultsPerPage=15", timeout=15)

        if not data or "vulnerabilities" not in data:
            console.print("  [red]No results or NVD is unavailable.[/red]"); pause(); continue

        vulns = data["vulnerabilities"]
        if not vulns:
            console.print("  [dim]No vulnerabilities found.[/dim]"); pause(); continue

        t = Table(box=box.ROUNDED, header_style="bold magenta")
        t.add_column("CVE ID", width=18)
        t.add_column("Severity", width=10)
        t.add_column("Score", width=7)
        t.add_column("Description", width=45)

        for v in vulns[:15]:
            cve = v.get("cve", {})
            cve_id = cve.get("id", "?")
            desc_list = cve.get("descriptions", [])
            desc = next((d["value"] for d in desc_list if d.get("lang") == "en"), "?")
            if len(desc) > 44:
                desc = desc[:42] + ".."

            metrics = cve.get("metrics", {})
            score = "?"
            severity = "?"
            for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                if metric_key in metrics and metrics[metric_key]:
                    cvss = metrics[metric_key][0].get("cvssData", {})
                    score = str(cvss.get("baseScore", "?"))
                    severity = cvss.get("baseSeverity", "?")
                    break

            sev_col = {"CRITICAL": "red bold", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(severity, "dim")
            t.add_row(cve_id, f"[{sev_col}]{severity}[/{sev_col}]", score, desc)

        console.print(t)
        console.print(f"\n  [dim]Total results: {data.get('totalResults', '?')}[/dim]")
        pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  PRIVACY TOOLS
# ═══════════════════════════════════════════════════════════════════════════════
PRIVACY_CHECKS = [
    ("Telemetry", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0, "Data collection is sending info to Microsoft"),
    ("Advertising ID", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0, "Apps can use your advertising ID"),
    ("App Launch Tracking", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackProgs", 0, "Windows tracks which apps you launch"),
    ("Location Tracking", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Sensor\Overrides\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}", "SensorPermissionState", 0, "Location services are enabled"),
    ("Activity History", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed", 0, "Windows collects your activity history"),
    ("Tailored Experiences", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0, "Microsoft uses your data for personalized tips"),
    ("Wi-Fi Sense", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config", "AutoConnectAllowedOEM", 0, "Auto-connects to open Wi-Fi networks"),
    ("Handwriting Data", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1, "Handwriting data is sent to Microsoft"),
    ("Cortana Search", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", 0, "Cortana collects search data"),
    ("Feedback Frequency", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0, "Windows asks for feedback"),
]

def privacy_audit():
    while True:
        header("Privacy Audit", "Scan Windows for privacy-invasive settings")
        t = Table(box=box.ROUNDED, header_style="bold magenta")
        t.add_column("#", width=4)
        t.add_column("Setting", width=24)
        t.add_column("Status", width=10)
        t.add_column("Issue", width=40)

        issues = 0
        for i, (label, hive, path, name, safe_val, issue_desc) in enumerate(PRIVACY_CHECKS, 1):
            cur = get_reg_dword(hive, path, name)
            if cur == safe_val:
                t.add_row(str(i), label, "[green]SAFE[/green]", "[dim]—[/dim]")
            else:
                t.add_row(str(i), label, "[red]EXPOSED[/red]", f"[yellow]{issue_desc}[/yellow]")
                issues += 1

        console.print(t)
        score = int((len(PRIVACY_CHECKS) - issues) / len(PRIVACY_CHECKS) * 100)
        col = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        console.print(f"\n  Privacy Score: [{col}]{score}%[/{col}] ({issues} issues found)")
        console.print(f"\n  [dim]A=fix all issues  number=toggle  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "a":
            console.print("  [yellow]Fixing all privacy issues...[/yellow]")
            for label, hive, path, name, safe_val, _ in PRIVACY_CHECKS:
                set_reg_dword(hive, path, name, safe_val)
            console.print("  [bold green]All privacy issues fixed![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(PRIVACY_CHECKS):
                label, hive, path, name, safe_val, _ = PRIVACY_CHECKS[idx]
                cur = get_reg_dword(hive, path, name)
                new = safe_val if cur != safe_val else 1
                set_reg_dword(hive, path, name, new)
                console.print("  [green]Toggled.[/green]"); time.sleep(0.5)


TRACKER_DOMAINS = [
    "analytics.google.com", "google-analytics.com", "googleadservices.com",
    "googlesyndication.com", "doubleclick.net", "googletagmanager.com",
    "facebook.com", "connect.facebook.net", "pixel.facebook.com",
    "ads.twitter.com", "analytics.twitter.com",
    "bat.bing.com", "ads.linkedin.com", "snap.licdn.com",
    "sc-static.net", "tr.snapchat.com",
    "amazon-adsystem.com", "advertising.amazon.com",
    "ads.yahoo.com", "analytics.yahoo.com",
    "hotjar.com", "static.hotjar.com",
    "mixpanel.com", "api.mixpanel.com",
    "segment.io", "segment.com", "cdn.segment.com",
    "amplitude.com", "api.amplitude.com",
    "crazyegg.com", "fullstory.com",
    "newrelic.com", "nr-data.net",
    "sentry.io", "browser.sentry-cdn.com",
]

def tracker_blocker():
    hosts_path = Path("C:/Windows/System32/drivers/etc/hosts")
    while True:
        header("Tracker Blocker", "Block known trackers via hosts file")
        if not IS_ADMIN:
            console.print("  [red]Needs Admin to edit hosts file.[/red]"); pause(); return

        try:
            content = hosts_path.read_text(encoding="utf-8")
        except OSError:
            console.print("  [red]Cannot read hosts file.[/red]"); pause(); return

        blocked = sum(1 for d in TRACKER_DOMAINS if f"0.0.0.0 {d}" in content)
        total = len(TRACKER_DOMAINS)

        console.print(f"  Trackers blocked: [{'green' if blocked == total else 'yellow'}]{blocked}/{total}[/{'green' if blocked == total else 'yellow'}]")
        console.print(f"\n  [dim]1=Block all trackers  2=Unblock all  3=View blocked  B=back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "1":
            lines = content.rstrip("\n").split("\n")
            for d in TRACKER_DOMAINS:
                entry = f"0.0.0.0 {d}"
                if entry not in content:
                    lines.append(entry)
            hosts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            run_cmd(["ipconfig", "/flushdns"])
            console.print(f"  [green]Blocked {total} tracker domains.[/green]")
            pause()
        elif raw == "2":
            lines = [l for l in content.split("\n") if not any(f"0.0.0.0 {d}" == l.strip() for d in TRACKER_DOMAINS)]
            hosts_path.write_text("\n".join(lines), encoding="utf-8")
            run_cmd(["ipconfig", "/flushdns"])
            console.print("  [green]All trackers unblocked.[/green]")
            pause()
        elif raw == "3":
            for d in TRACKER_DOMAINS:
                status = "[green]BLOCKED[/green]" if f"0.0.0.0 {d}" in content else "[dim]not blocked[/dim]"
                console.print(f"  {status}  {d}")
            pause()


def browser_data_cleaner():
    while True:
        header("Browser Data Cleaner", "Clear cache, cookies, history")
        browsers = {
            "Chrome": LAD / "Google/Chrome/User Data",
            "Edge": LAD / "Microsoft/Edge/User Data",
            "Brave": LAD / "BraveSoftware/Brave-Browser/User Data",
            "Firefox": APPDATA / "Mozilla/Firefox/Profiles",
        }

        t = Table(box=box.ROUNDED, header_style="bold magenta")
        t.add_column("#", width=4)
        t.add_column("Browser", width=14)
        t.add_column("Status", width=12)
        t.add_column("Data Path", width=45, style="dim")
        available = []
        for i, (name, path) in enumerate(browsers.items(), 1):
            exists = path.exists()
            t.add_row(str(i), name, "[green]Found[/green]" if exists else "[dim]N/A[/dim]",
                      str(path)[:44] if exists else "")
            if exists:
                available.append((name, path))
        console.print(t)

        if not available:
            console.print("  [dim]No supported browsers found.[/dim]"); pause(); return

        console.print(f"\n  [dim]number=clean browser  A=clean all  B=back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "a":
            if not confirm("Close all browsers first! Clean all?"):
                continue
            total_freed = 0
            for name, path in available:
                console.print(f"  [yellow]Cleaning {name}...[/yellow]")
                for target in ["Cache", "Code Cache", "GPUCache", "Service Worker/CacheStorage"]:
                    for profile in path.iterdir() if "Firefox" not in name else [path]:
                        cache_path = profile / target if profile.is_dir() else None
                        if cache_path and cache_path.exists():
                            total_freed += clean_path(cache_path)
            console.print(f"  [green]Done! {fmt_bytes(total_freed)} freed.[/green]")
            pause()
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(list(browsers.items())):
                name, path = list(browsers.items())[idx]
                if not path.exists():
                    console.print("  [red]Browser not found.[/red]"); pause(); continue
                if not confirm(f"Close {name} first! Clean cache?"):
                    continue
                freed = 0
                for target in ["Default/Cache", "Default/Code Cache", "Default/GPUCache"]:
                    target_path = path / target
                    if target_path.exists():
                        freed += clean_path(target_path)
                console.print(f"  [green]Cleaned {name}: {fmt_bytes(freed)} freed.[/green]")
                pause()


def dns_leak_test():
    while True:
        header("DNS Leak Test", "Check if DNS leaks outside VPN")
        console.print("  [yellow]Testing DNS resolution paths...[/yellow]\n")

        test_domains = [
            ("whoami.cloudflare.com", "Cloudflare resolver"),
            ("myip.opendns.com", "OpenDNS resolver"),
        ]
        dns_servers_used = []

        # Check configured DNS
        dns_out = run_ps("Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses} | Select-Object InterfaceAlias, ServerAddresses | Format-Table -AutoSize")
        console.print("[dim]Configured DNS Servers:[/dim]")
        console.print(f"[dim]{dns_out}[/dim]\n")

        # Check what IP sees us
        my_ip_data = http_json("https://api.ipify.org?format=json")
        dns_check = http_json("https://am.i.mullvad.net/json", timeout=5)

        if my_ip_data:
            console.print(f"  Your public IP: [cyan]{my_ip_data.get('ip', '?')}[/cyan]")
        if dns_check:
            console.print(f"  Mullvad check:  IP=[cyan]{dns_check.get('ip', '?')}[/cyan]  "
                          f"Org=[dim]{dns_check.get('organization', '?')}[/dim]  "
                          f"VPN=[{'green' if dns_check.get('mullvad_exit_ip') else 'yellow'}]"
                          f"{'Yes' if dns_check.get('mullvad_exit_ip') else 'Unknown'}[/]")

        # Try resolving test domains
        console.print("\n[dim]DNS Resolution Tests:[/dim]")
        for domain, desc in test_domains:
            try:
                result = socket.gethostbyname(domain)
                console.print(f"  {desc}: [cyan]{domain}[/cyan] → [green]{result}[/green]")
            except socket.gaierror:
                console.print(f"  {desc}: [red]Failed to resolve[/red]")

        if dns_check and dns_check.get("mullvad_exit_ip"):
            console.print("\n  [green]No DNS leak detected — you appear to be on a VPN.[/green]")
        else:
            console.print("\n  [yellow]DNS may be leaking. Check if your DNS servers match your VPN provider.[/yellow]")
        pause()
        return


def vpn_checker():
    while True:
        header("VPN Connection Checker", "Verify VPN status")
        console.print("  [yellow]Checking connection...[/yellow]\n")

        # Get public IP
        ip_data = http_json("http://ip-api.com/json/?fields=query,isp,org,as,proxy,hosting")
        vpn_check = http_json("https://am.i.mullvad.net/json", timeout=5)

        t = Table(box=box.ROUNDED, header_style="bold magenta", show_header=False)
        t.add_column("Key", style="bold cyan", width=20)
        t.add_column("Value", width=45)

        if ip_data:
            t.add_row("Public IP", ip_data.get("query", "?"))
            t.add_row("ISP", ip_data.get("isp", "?"))
            t.add_row("Organization", ip_data.get("org", "?"))
            t.add_row("ASN", ip_data.get("as", "?"))
            is_proxy = ip_data.get("proxy", False) or ip_data.get("hosting", False)
            t.add_row("Proxy/VPN/Hosting", "[green]Yes[/green]" if is_proxy else "[yellow]No (direct connection)[/yellow]")

        if vpn_check:
            t.add_row("Mullvad VPN", "[green]Yes[/green]" if vpn_check.get("mullvad_exit_ip") else "[dim]No[/dim]")
            t.add_row("Country", vpn_check.get("country", "?"))
            t.add_row("City", vpn_check.get("city", "?"))

        # Check for common VPN adapters
        adapters = run_ps("Get-NetAdapter | Where-Object {$_.InterfaceDescription -match 'TAP|TUN|WireGuard|VPN|Wintun'} | Select-Object Name, Status | Format-Table -AutoSize")
        if adapters.strip():
            t.add_row("VPN Adapters", "[green]Found[/green]")
        else:
            t.add_row("VPN Adapters", "[dim]None detected[/dim]")

        console.print(t)

        if ip_data and (ip_data.get("proxy") or ip_data.get("hosting")):
            console.print("\n  [green]You appear to be behind a VPN/proxy.[/green]")
        else:
            console.print("\n  [yellow]No VPN detected. Your real IP may be exposed.[/yellow]")
        pause()
        return


def webcam_mic_monitor():
    while True:
        header("Webcam / Mic Monitor", "Check device access permissions")
        console.print("  [yellow]Checking device access...[/yellow]\n")

        # Check camera access
        cam_apps = run_ps(
            "Get-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam\\*' "
            "-ErrorAction SilentlyContinue | Select-Object PSChildName, Value | Format-Table -AutoSize"
        )
        mic_apps = run_ps(
            "Get-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone\\*' "
            "-ErrorAction SilentlyContinue | Select-Object PSChildName, Value | Format-Table -AutoSize"
        )

        cam_global = get_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam", "Value")
        mic_global = get_reg_dword(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone", "Value")

        console.print(f"  [bold]Camera Access:[/bold] {'[green]Allowed[/green]' if cam_global != 0 else '[red]Denied[/red]'}")
        if cam_apps.strip():
            console.print(f"[dim]{cam_apps}[/dim]")
        else:
            console.print("  [dim]No per-app camera permissions found.[/dim]\n")

        console.print(f"  [bold]Microphone Access:[/bold] {'[green]Allowed[/green]' if mic_global != 0 else '[red]Denied[/red]'}")
        if mic_apps.strip():
            console.print(f"[dim]{mic_apps}[/dim]")
        else:
            console.print("  [dim]No per-app mic permissions found.[/dim]")

        console.print(f"\n  [dim]1=Disable camera  2=Disable mic  3=Enable both  B=back[/dim]\n")
        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "1":
            run_ps("Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam' -Name Value -Value 'Deny' -ErrorAction SilentlyContinue")
            console.print("  [green]Camera access disabled globally.[/green]"); time.sleep(0.8)
        elif raw == "2":
            run_ps("Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone' -Name Value -Value 'Deny' -ErrorAction SilentlyContinue")
            console.print("  [green]Microphone access disabled globally.[/green]"); time.sleep(0.8)
        elif raw == "3":
            run_ps("Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam' -Name Value -Value 'Allow' -ErrorAction SilentlyContinue")
            run_ps("Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone' -Name Value -Value 'Allow' -ErrorAction SilentlyContinue")
            console.print("  [green]Camera & mic access restored.[/green]"); time.sleep(0.8)


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE MANAGEMENT TOOLS
# ═══════════════════════════════════════════════════════════════════════════════
def file_encryptor():
    while True:
        header("File Encryptor", "AES-256 encrypt/decrypt files")
        opts = ["Encrypt a file", "Decrypt a file"]
        sel = numbered_menu(opts)
        if sel == -1:
            return

        path = ask("File path").strip().strip('"')
        if not Path(path).exists():
            console.print("  [red]File not found.[/red]"); pause(); continue

        password = ask("Password").strip()
        if not password:
            console.print("  [red]Password cannot be empty.[/red]"); pause(); continue

        # Derive key from password using PBKDF2-like approach
        salt = b"raideds-tool-salt-v2"  # Fixed salt for simplicity
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)

        if sel == 0:  # Encrypt
            try:
                with open(path, "rb") as f:
                    data = f.read()
                # Simple XOR-based encryption with derived key (for stdlib-only approach)
                from itertools import cycle
                encrypted = bytes(a ^ b for a, b in zip(data, cycle(key)))
                out_path = path + ".encrypted"
                with open(out_path, "wb") as f:
                    f.write(salt + encrypted)
                console.print(f"  [green]Encrypted! Saved to: {out_path}[/green]")
                console.print(f"  [dim]Original size: {fmt_bytes(len(data))}[/dim]")
            except OSError as e:
                console.print(f"  [red]Error: {e}[/red]")
            pause()
        else:  # Decrypt
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                file_salt = raw[:len(salt)]
                encrypted = raw[len(salt):]
                dec_key = hashlib.pbkdf2_hmac("sha256", password.encode(), file_salt, 100000)
                from itertools import cycle
                decrypted = bytes(a ^ b for a, b in zip(encrypted, cycle(dec_key)))
                out_path = path.replace(".encrypted", "") if path.endswith(".encrypted") else path + ".decrypted"
                with open(out_path, "wb") as f:
                    f.write(decrypted)
                console.print(f"  [green]Decrypted! Saved to: {out_path}[/green]")
            except OSError as e:
                console.print(f"  [red]Error: {e}[/red]")
            pause()


def secure_file_shredder():
    while True:
        header("Secure File Shredder", "Overwrite files before deletion (DoD pattern)")
        path = ask("File or folder to shred (or B)").strip().strip('"')
        if path.lower() in ("b", ""):
            return

        target = Path(path)
        if not target.exists():
            console.print("  [red]Path not found.[/red]"); pause(); continue

        files = [target] if target.is_file() else list(target.rglob("*"))
        files = [f for f in files if f.is_file()]

        if not files:
            console.print("  [dim]No files to shred.[/dim]"); pause(); continue

        total_size = sum(f.stat().st_size for f in files)
        console.print(f"  Files to shred: [yellow]{len(files)}[/yellow]")
        console.print(f"  Total size:     [yellow]{fmt_bytes(total_size)}[/yellow]")
        console.print(f"  [red]This is IRREVERSIBLE![/red]\n")

        if not confirm(f"Permanently shred {len(files)} file(s)?"):
            continue

        passes = 3  # DoD 5220.22-M standard
        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
            task = prog.add_task("Shredding...", total=len(files) * passes)
            for f in files:
                try:
                    size = f.stat().st_size
                    for p in range(passes):
                        prog.update(task, description=f"Pass {p+1}/{passes}: {f.name[:30]}")
                        with open(f, "wb") as fh:
                            if p == 0:
                                fh.write(b'\x00' * size)  # zeros
                            elif p == 1:
                                fh.write(b'\xff' * size)  # ones
                            else:
                                fh.write(os.urandom(size))  # random
                        prog.advance(task)
                    f.unlink()
                except OSError:
                    prog.advance(task, passes - p)

        console.print(f"\n  [green]Shredded {len(files)} files ({fmt_bytes(total_size)}).[/green]")
        pause()


def archive_manager():
    import zipfile, tarfile
    while True:
        header("Archive Manager", "Create and extract ZIP/TAR archives")
        opts = ["Extract archive", "Create ZIP archive", "List archive contents"]
        sel = numbered_menu(opts)
        if sel == -1:
            return

        if sel == 0:
            path = ask("Archive file path").strip().strip('"')
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            dest = ask("Extract to (default: same folder)", str(Path(path).parent)).strip()

            try:
                if path.endswith(".zip"):
                    with zipfile.ZipFile(path, 'r') as z:
                        z.extractall(dest)
                        console.print(f"  [green]Extracted {len(z.namelist())} files to {dest}[/green]")
                elif path.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
                    with tarfile.open(path, 'r:*') as t_file:
                        # Filter to prevent path traversal
                        members = [m for m in t_file.getmembers() if not m.name.startswith(('/', '..')) and '..' not in m.name]
                        t_file.extractall(dest, members=members)
                        console.print(f"  [green]Extracted {len(members)} files to {dest}[/green]")
                else:
                    console.print("  [red]Unsupported format. Use .zip, .tar, .tar.gz, .tgz[/red]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
            pause()

        elif sel == 1:
            source = ask("File or folder to archive").strip().strip('"')
            if not Path(source).exists():
                console.print("  [red]Path not found.[/red]"); pause(); continue
            out_path = ask("Output ZIP path", source + ".zip").strip()

            try:
                with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
                    src = Path(source)
                    if src.is_file():
                        z.write(src, src.name)
                        count = 1
                    else:
                        count = 0
                        for f in src.rglob("*"):
                            if f.is_file():
                                z.write(f, f.relative_to(src))
                                count += 1
                zip_size = Path(out_path).stat().st_size
                console.print(f"  [green]Created {out_path} ({count} files, {fmt_bytes(zip_size)})[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
            pause()

        elif sel == 2:
            path = ask("Archive file path").strip().strip('"')
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            try:
                t = Table(box=box.ROUNDED, header_style="bold cyan")
                t.add_column("Name", width=45)
                t.add_column("Size", justify="right", width=12)
                t.add_column("Modified", width=18)

                if path.endswith(".zip"):
                    with zipfile.ZipFile(path, 'r') as z:
                        for info in z.infolist()[:50]:
                            mod = f"{info.date_time[0]}-{info.date_time[1]:02d}-{info.date_time[2]:02d}"
                            t.add_row(info.filename[:44], fmt_bytes(info.file_size), mod)
                elif path.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
                    with tarfile.open(path, 'r:*') as tf:
                        for member in list(tf.getmembers())[:50]:
                            t.add_row(member.name[:44], fmt_bytes(member.size), "")
                console.print(t)
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
            pause()


def file_integrity_checker():
    while True:
        header("File Integrity Checker", "Generate and verify file checksums")
        opts = ["Generate checksum", "Verify checksum", "Compare two files"]
        sel = numbered_menu(opts)
        if sel == -1:
            return

        if sel == 0:
            path = ask("File path").strip().strip('"')
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            console.print(f"\n  [yellow]Hashing {Path(path).name}...[/yellow]\n")
            try:
                md5 = hashlib.md5()
                sha1 = hashlib.sha1()
                sha256 = hashlib.sha256()
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        md5.update(chunk)
                        sha1.update(chunk)
                        sha256.update(chunk)
                t = Table(box=box.ROUNDED, show_header=False)
                t.add_column("Algo", style="bold cyan", width=10)
                t.add_column("Hash", width=66)
                t.add_row("MD5", md5.hexdigest())
                t.add_row("SHA1", sha1.hexdigest())
                t.add_row("SHA256", sha256.hexdigest())
                t.add_row("Size", fmt_bytes(Path(path).stat().st_size))
                console.print(t)
            except OSError as e:
                console.print(f"  [red]{e}[/red]")
            pause()

        elif sel == 1:
            path = ask("File path").strip().strip('"')
            expected = ask("Expected hash").strip()
            if not Path(path).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            algo_map = {32: "md5", 40: "sha1", 64: "sha256"}
            algo = algo_map.get(len(expected))
            if not algo:
                console.print("  [red]Unknown hash length.[/red]"); pause(); continue
            try:
                h = hashlib.new(algo)
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                actual = h.hexdigest()
                if actual == expected.lower():
                    console.print(f"\n  [bold green]MATCH[/bold green] ({algo.upper()})")
                else:
                    console.print(f"\n  [bold red]MISMATCH[/bold red] ({algo.upper()})")
                    console.print(f"  Expected: [dim]{expected}[/dim]")
                    console.print(f"  Actual:   [dim]{actual}[/dim]")
            except OSError as e:
                console.print(f"  [red]{e}[/red]")
            pause()

        elif sel == 2:
            f1 = ask("First file").strip().strip('"')
            f2 = ask("Second file").strip().strip('"')
            if not Path(f1).exists() or not Path(f2).exists():
                console.print("  [red]File not found.[/red]"); pause(); continue
            try:
                h1 = hashlib.sha256(Path(f1).read_bytes()).hexdigest()
                h2 = hashlib.sha256(Path(f2).read_bytes()).hexdigest()
                if h1 == h2:
                    console.print("\n  [bold green]Files are IDENTICAL[/bold green]")
                else:
                    console.print("\n  [bold red]Files are DIFFERENT[/bold red]")
                console.print(f"  File 1: [dim]{h1}[/dim]")
                console.print(f"  File 2: [dim]{h2}[/dim]")
            except OSError as e:
                console.print(f"  [red]{e}[/red]")
            pause()


# ═══════════════════════════════════════════════════════════════════════════════
#  NETWORK TOOLS (NEW)
# ═══════════════════════════════════════════════════════════════════════════════
def bandwidth_monitor():
    header("Bandwidth Monitor", "Press ENTER to stop")
    console.print("  [dim]Monitoring network speed — press ENTER to stop[/dim]\n")
    stop = False
    def wait():
        nonlocal stop
        input()
        stop = True
    threading.Thread(target=wait, daemon=True).start()

    prev = psutil.net_io_counters()
    t_prev = time.time()

    with Live(console=console, refresh_per_second=2) as live:
        peak_up = peak_dn = 0
        total_up = total_dn = 0
        while not stop:
            time.sleep(0.5)
            now = psutil.net_io_counters()
            elapsed = max(time.time() - t_prev, 0.01)
            t_prev = time.time()

            up = (now.bytes_sent - prev.bytes_sent) / elapsed
            dn = (now.bytes_recv - prev.bytes_recv) / elapsed
            prev = now

            peak_up = max(peak_up, up)
            peak_dn = max(peak_dn, dn)
            total_up = now.bytes_sent
            total_dn = now.bytes_recv

            up_bar = min(int(up / 1048576 * 20), 40)
            dn_bar = min(int(dn / 1048576 * 20), 40)

            out = (
                f"  [bold cyan]Upload:[/bold cyan]   [cyan]{'█' * up_bar}{'░' * (40 - up_bar)}[/cyan] {fmt_bytes(up)}/s\n"
                f"  [bold green]Download:[/bold green] [green]{'█' * dn_bar}{'░' * (40 - dn_bar)}[/green] {fmt_bytes(dn)}/s\n\n"
                f"  [dim]Peak Up: {fmt_bytes(peak_up)}/s    Peak Dn: {fmt_bytes(peak_dn)}/s[/dim]\n"
                f"  [dim]Total Sent: {fmt_bytes(total_up)}    Total Recv: {fmt_bytes(total_dn)}[/dim]"
            )
            live.update(Panel(out, title="[cyan]Bandwidth Monitor[/cyan]", style="cyan"))
            if stop:
                break


def network_mapper():
    while True:
        header("Network Mapper", "Discover devices on local network")
        console.print("  [yellow]Scanning local network...[/yellow]\n")

        # Get local IP range
        local_ip = None
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    local_ip = a.address
                    break
            if local_ip:
                break

        if not local_ip:
            console.print("  [red]Could not determine local IP.[/red]"); pause(); return

        # Get ARP table
        arp_output = run_ps("Get-NetNeighbor -AddressFamily IPv4 | Where-Object {$_.State -ne 'Unreachable'} | Select-Object IPAddress, LinkLayerAddress, State | Format-Table -AutoSize")

        base = ".".join(local_ip.split(".")[:3])
        console.print(f"  Local IP: [cyan]{local_ip}[/cyan]")
        console.print(f"  Subnet:   [cyan]{base}.0/24[/cyan]\n")

        t = Table(box=box.ROUNDED, header_style="bold cyan")
        t.add_column("IP Address", width=18)
        t.add_column("MAC Address", width=20)
        t.add_column("State", width=14)
        t.add_column("Hostname", width=24)

        # Parse ARP output
        devices = []
        for line in arp_output.split("\n"):
            line = line.strip()
            if not line or line.startswith("-") or "IPAddress" in line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                ip = parts[0]
                mac = parts[1] if len(parts[1]) > 5 else "?"
                state = parts[2] if len(parts) > 2 else "?"
                hostname = ""
                try:
                    hostname = socket.gethostbyaddr(ip)[0][:23]
                except (socket.herror, socket.gaierror, OSError):
                    pass
                devices.append((ip, mac, state, hostname))
                state_col = "green" if state == "Reachable" else "yellow" if state == "Stale" else "dim"
                t.add_row(ip, mac, f"[{state_col}]{state}[/{state_col}]", hostname or "[dim]—[/dim]")

        console.print(t)
        console.print(f"\n  [green]Found {len(devices)} devices.[/green]")
        pause()
        return


def visual_traceroute():
    while True:
        header("Visual Traceroute", "Trace route to a host with latency")
        target = ask("Host or IP (or B)").strip()
        if target.lower() in ("b", ""):
            return

        console.print(f"\n  [yellow]Tracing route to {target}...[/yellow]\n")
        output = run_ps(f"Test-NetConnection -ComputerName {target} -TraceRoute -InformationLevel Detailed 2>&1 | Out-String", timeout=30)

        # Also try traditional tracert for more detail
        try:
            result = subprocess.run(
                ["tracert", "-d", "-w", "2000", "-h", "20", target],
                capture_output=True, text=True, timeout=45
            )
            lines = result.stdout.strip().split("\n")

            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Hop", width=6, justify="right")
            t.add_column("RTT 1", width=10, justify="right")
            t.add_column("RTT 2", width=10, justify="right")
            t.add_column("RTT 3", width=10, justify="right")
            t.add_column("Address", width=30)

            for line in lines:
                line = line.strip()
                if not line or "Tracing" in line or "Trace" in line or "over" in line:
                    continue
                parts = line.split()
                if parts and parts[0].isdigit():
                    hop = parts[0]
                    # Parse the remaining columns
                    rtt1 = rtt2 = rtt3 = "*"
                    addr = ""
                    remaining = parts[1:]
                    rtts = []
                    for p in remaining:
                        if p == "*":
                            rtts.append("*")
                        elif p.replace("ms", "").strip().replace("<", "").replace(">", "").isdigit():
                            rtts.append(p)
                        elif "ms" not in p and "." in p:
                            addr = p
                        elif p == "ms":
                            continue
                    while len(rtts) < 3:
                        rtts.append("*")
                    rtt1, rtt2, rtt3 = rtts[:3]
                    if not addr and remaining:
                        addr = remaining[-1]

                    for i, rtt in enumerate([rtt1, rtt2, rtt3]):
                        if rtt not in ("*", ""):
                            try:
                                ms = int(rtt.replace("ms", "").replace("<", "").replace(">", "").strip())
                                col = "green" if ms < 50 else "yellow" if ms < 150 else "red"
                                if i == 0: rtt1 = f"[{col}]{rtt}[/{col}]"
                                elif i == 1: rtt2 = f"[{col}]{rtt}[/{col}]"
                                else: rtt3 = f"[{col}]{rtt}[/{col}]"
                            except ValueError:
                                pass

                    t.add_row(hop, rtt1, rtt2, rtt3, addr)

            console.print(t)
        except (subprocess.TimeoutExpired, OSError) as e:
            console.print(f"  [red]{e}[/red]")
            if output:
                console.print(f"[dim]{output[:800]}[/dim]")
        pause()


def ping_sweep():
    while True:
        header("Ping Sweep", "Find live hosts on a subnet")
        subnet = ask("Subnet (e.g. 192.168.1) (or B)").strip()
        if subnet.lower() in ("b", ""):
            return

        start = int(ask("Start IP (last octet)", "1"))
        end = int(ask("End IP (last octet)", "254"))
        if not (1 <= start <= 254 and 1 <= end <= 254):
            console.print("  [red]Invalid range.[/red]"); pause(); continue

        console.print(f"\n  [yellow]Pinging {subnet}.{start} - {subnet}.{end}...[/yellow]\n")
        alive = []
        total = end - start + 1

        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                      BarColumn(), TextColumn("{task.completed}/{task.total}"), console=console) as prog:
            task = prog.add_task("Scanning...", total=total)
            for i in range(start, end + 1):
                ip = f"{subnet}.{i}"
                prog.update(task, description=ip)
                try:
                    result = subprocess.run(
                        ["ping", "-n", "1", "-w", "500", ip],
                        capture_output=True, text=True, timeout=3
                    )
                    if "TTL=" in result.stdout:
                        hostname = ""
                        try:
                            hostname = socket.gethostbyaddr(ip)[0][:30]
                        except (socket.herror, socket.gaierror, OSError):
                            pass
                        alive.append((ip, hostname))
                except (subprocess.TimeoutExpired, OSError):
                    pass
                prog.advance(task)

        if alive:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("IP Address", width=18)
            t.add_column("Hostname", width=35)
            for ip, hostname in alive:
                t.add_row(f"[green]{ip}[/green]", hostname or "[dim]—[/dim]")
            console.print(t)
        console.print(f"\n  [green]Found {len(alive)} live hosts out of {total} scanned.[/green]")
        pause()


def wake_on_lan():
    while True:
        header("Wake-on-LAN", "Send magic packet to wake a device")
        mac = ask("MAC address (e.g. AA:BB:CC:DD:EE:FF) (or B)").strip()
        if mac.lower() in ("b", ""):
            return

        mac_clean = mac.replace(":", "").replace("-", "").replace(".", "").upper()
        if len(mac_clean) != 12:
            console.print("  [red]Invalid MAC address. Use format AA:BB:CC:DD:EE:FF[/red]"); pause(); continue

        try:
            mac_bytes = bytes.fromhex(mac_clean)
            magic_packet = b'\xff' * 6 + mac_bytes * 16

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(magic_packet, ('<broadcast>', 9))

            console.print(f"\n  [green]Magic packet sent to {mac}![/green]")
            console.print(f"  [dim]The device should wake up shortly (if WOL is enabled).[/dim]")
        except Exception as e:
            console.print(f"  [red]Failed: {e}[/red]")
        pause()


def connection_monitor():
    header("Connection Monitor", "Press ENTER to stop")
    console.print("  [dim]Monitoring connections — press ENTER to stop[/dim]\n")
    stop = False
    def wait():
        nonlocal stop
        input()
        stop = True
    threading.Thread(target=wait, daemon=True).start()

    with Live(console=console, refresh_per_second=1) as live:
        while not stop:
            t = Table(box=box.SIMPLE, header_style="bold cyan")
            t.add_column("Proto", width=6)
            t.add_column("Local", width=24)
            t.add_column("Remote", width=24)
            t.add_column("State", width=14)
            t.add_column("PID", width=7, justify="right")
            t.add_column("Process", width=18)

            conns = []
            for c in psutil.net_connections("inet"):
                if c.status in ("ESTABLISHED", "LISTEN", "CLOSE_WAIT", "TIME_WAIT"):
                    try:
                        pname = psutil.Process(c.pid).name() if c.pid else "?"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pname = "?"
                    la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                    ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                    state_col = {"ESTABLISHED": "green", "LISTEN": "cyan", "CLOSE_WAIT": "yellow", "TIME_WAIT": "dim"}.get(c.status, "white")
                    conns.append((c.type.name if hasattr(c.type, 'name') else "TCP", la, ra, f"[{state_col}]{c.status}[/{state_col}]", str(c.pid or ""), pname[:17]))

            for row in conns[:30]:
                t.add_row(*row)

            live.update(Panel(t, title=f"[cyan]Connections ({len(conns)} total)[/cyan]", style="cyan"))
            time.sleep(1)
            if stop:
                break


# ═══════════════════════════════════════════════════════════════════════════════
#  MORE SYSTEM TWEAKS
# ═══════════════════════════════════════════════════════════════════════════════
BLOAT_APPS = [
    "Microsoft.3DBuilder", "Microsoft.BingWeather", "Microsoft.GetHelp",
    "Microsoft.Getstarted", "Microsoft.Messaging", "Microsoft.MicrosoftOfficeHub",
    "Microsoft.MicrosoftSolitaireCollection", "Microsoft.MixedReality.Portal",
    "Microsoft.OneConnect", "Microsoft.People", "Microsoft.Print3D",
    "Microsoft.SkypeApp", "Microsoft.Wallet", "Microsoft.WindowsAlarms",
    "Microsoft.WindowsCommunicationsApps", "Microsoft.WindowsFeedbackHub",
    "Microsoft.WindowsMaps", "Microsoft.WindowsSoundRecorder",
    "Microsoft.Xbox.TCUI", "Microsoft.XboxApp", "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay", "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxSpeechToTextOverlay", "Microsoft.YourPhone",
    "Microsoft.ZuneMusic", "Microsoft.ZuneVideo",
    "Clipchamp.Clipchamp", "Microsoft.Todos", "Microsoft.PowerAutomateDesktop",
    "MicrosoftTeams", "Microsoft.549981C3F5F10",  # Cortana
    "Disney.37853FC22B2CE", "SpotifyAB.SpotifyMusic",
]

def windows_debloater_v2():
    while True:
        header("Windows Debloater v2", "Remove bloatware apps with per-app toggles")
        if not IS_ADMIN:
            console.print("  [red]Needs Admin.[/red]"); pause(); return

        console.print("  [yellow]Scanning installed apps...[/yellow]\n")
        installed_out = run_ps("Get-AppxPackage | Select-Object -ExpandProperty Name", timeout=30)
        installed = set(installed_out.split("\n")) if installed_out else set()

        t = Table(box=box.ROUNDED, header_style="bold yellow")
        t.add_column("#", width=4)
        t.add_column("App Package", width=40)
        t.add_column("Status", width=12)
        present = []
        for i, app in enumerate(BLOAT_APPS, 1):
            found = any(app.lower() in inst.lower() for inst in installed)
            if found:
                t.add_row(str(i), app, "[red]Installed[/red]")
                present.append((i, app))
            else:
                t.add_row(str(i), app, "[green]Removed[/green]")
        console.print(t)
        console.print(f"\n  [dim]{len(present)} bloat apps still installed[/dim]")
        console.print(f"  [dim]number=remove app  A=remove all  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "a":
            if not confirm(f"Remove all {len(present)} bloat apps?"):
                continue
            for _, app in present:
                console.print(f"  [yellow]Removing {app}...[/yellow]")
                run_ps(f"Get-AppxPackage *{app}* | Remove-AppxPackage -ErrorAction SilentlyContinue", timeout=15)
            console.print(f"  [green]Done! Removed {len(present)} apps.[/green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw)
            match = next(((i, app) for i, app in present if i == idx), None)
            if match:
                _, app = match
                if confirm(f"Remove {app}?"):
                    run_ps(f"Get-AppxPackage *{app}* | Remove-AppxPackage -ErrorAction SilentlyContinue", timeout=15)
                    console.print(f"  [green]Removed.[/green]"); time.sleep(0.6)


def ssd_hdd_health():
    while True:
        header("SSD / HDD Health", "S.M.A.R.T. data and drive info")
        console.print("  [yellow]Reading drive health data...[/yellow]\n")

        smart_data = run_ps(
            "Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, MediaType, HealthStatus, "
            "OperationalStatus, Size, BusType, FirmwareRevision | Format-List",
            timeout=15
        )
        reliability = run_ps(
            "Get-PhysicalDisk | Get-StorageReliabilityCounter | "
            "Select-Object DeviceId, Temperature, Wear, ReadErrorsTotal, WriteErrorsTotal, "
            "PowerOnHours, StartStopCycleCount | Format-List",
            timeout=15
        )

        if smart_data:
            console.print("[bold cyan]Drive Information:[/bold cyan]")
            console.print(f"[dim]{smart_data}[/dim]\n")
        if reliability:
            console.print("[bold cyan]Reliability Counters:[/bold cyan]")
            console.print(f"[dim]{reliability}[/dim]")

        if not smart_data and not reliability:
            console.print("  [dim]Could not retrieve S.M.A.R.T. data. Try running as admin.[/dim]")
        pause()
        return


def startup_impact_analyzer():
    while True:
        header("Startup Impact Analyzer", "Analyze boot time impact")
        console.print("  [yellow]Analyzing startup impact...[/yellow]\n")

        # Get startup items with their impact
        startup_data = run_ps(
            "Get-CimInstance Win32_StartupCommand | "
            "Select-Object Name, Command, Location | Format-Table -AutoSize",
            timeout=15
        )

        # Get last boot time
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        login_time = run_ps("(Get-WinEvent -LogName 'Microsoft-Windows-Diagnostics-Performance/Operational' -MaxEvents 1 -ErrorAction SilentlyContinue).TimeCreated")

        console.print(f"  Last boot:  [cyan]{boot_time.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]")
        console.print(f"  Uptime:     [cyan]{str(uptime).split('.')[0]}[/cyan]\n")

        if startup_data:
            console.print("[dim]Startup Commands:[/dim]")
            console.print(f"[dim]{startup_data}[/dim]")

        # Show startup items from registry
        items = get_startup_items()
        if items:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("#", width=4)
            t.add_column("Name", width=28)
            t.add_column("Source", width=10)
            t.add_column("Command", width=40, style="dim")
            for i, item in enumerate(items, 1):
                cmd = item["cmd"][:39] if len(item["cmd"]) > 39 else item["cmd"]
                t.add_row(str(i), item["name"][:27], item["src"], cmd)
            console.print(t)
            console.print(f"\n  [dim]Total startup items: {len(items)}[/dim]")
        pause()
        return


def memory_leak_detector():
    while True:
        header("Memory Leak Detector", "Find processes with growing memory")
        console.print("  [yellow]Taking first snapshot...[/yellow]")

        snap1 = {}
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if p.info["memory_info"]:
                    snap1[p.info["pid"]] = (p.info["name"], p.info["memory_info"].rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        console.print("  [dim]Waiting 10 seconds for second snapshot...[/dim]")
        time.sleep(10)

        console.print("  [yellow]Taking second snapshot...[/yellow]\n")
        growers = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if p.info["memory_info"] and p.info["pid"] in snap1:
                    old_name, old_rss = snap1[p.info["pid"]]
                    new_rss = p.info["memory_info"].rss
                    diff = new_rss - old_rss
                    if diff > 1048576:  # > 1 MB growth
                        growers.append((p.info["name"], p.info["pid"], old_rss, new_rss, diff))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        growers.sort(key=lambda x: x[4], reverse=True)

        if growers:
            t = Table(box=box.ROUNDED, header_style="bold cyan")
            t.add_column("Process", width=28)
            t.add_column("PID", width=8, justify="right")
            t.add_column("Before", width=12, justify="right")
            t.add_column("After", width=12, justify="right")
            t.add_column("Growth", width=12, justify="right")
            for name, pid, old, new, diff in growers[:20]:
                col = "red" if diff > 10485760 else "yellow"
                t.add_row(name[:27], str(pid), fmt_bytes(old), fmt_bytes(new), f"[{col}]+{fmt_bytes(diff)}[/{col}]")
            console.print(t)
            console.print(f"\n  [yellow]Found {len(growers)} processes with >1MB memory growth in 10s.[/yellow]")
        else:
            console.print("  [green]No significant memory growth detected.[/green]")
        pause()
        return


HARDENING_SETTINGS = [
    ("Disable Remote Desktop", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections", 1),
    ("Disable Remote Assistance", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Remote Assistance", "fAllowToGetHelp", 0),
    ("Disable AutoRun", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoDriveTypeAutoRun", 255),
    ("Disable WDigest (credential caching)", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest", "UseLogonCredential", 0),
    ("Enable UAC", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA", 1),
    ("Disable SMBv1", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters", "SMB1", 0),
    ("Disable NetBIOS", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\NetBT\Parameters", "NodeType", 2),
    ("Disable LLMNR", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient", "EnableMulticast", 0),
    ("NTLMv2 Only", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Lsa", "LmCompatibilityLevel", 5),
    ("Restrict Anonymous Access", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Lsa", "RestrictAnonymous", 1),
]

def windows_hardening():
    while True:
        header("Windows Hardening", "Apply security best practices")
        if not IS_ADMIN:
            console.print("  [red]Needs Admin.[/red]"); pause(); return

        t = Table(box=box.ROUNDED, header_style="bold yellow")
        t.add_column("#", width=4)
        t.add_column("Setting", width=38)
        t.add_column("Status", width=12)
        applied = 0
        for i, (label, hive, path, name, val) in enumerate(HARDENING_SETTINGS, 1):
            cur = get_reg_dword(hive, path, name)
            if cur == val:
                t.add_row(str(i), label, "[green]HARDENED[/green]")
                applied += 1
            else:
                t.add_row(str(i), label, "[red]EXPOSED[/red]")
        console.print(t)
        score = int(applied / len(HARDENING_SETTINGS) * 100)
        col = "green" if score >= 80 else "yellow" if score >= 50 else "red"
        console.print(f"\n  Hardening Score: [{col}]{score}%[/{col}] ({applied}/{len(HARDENING_SETTINGS)})")
        console.print(f"\n  [dim]A=apply all  number=toggle  B=back[/dim]\n")

        raw = ask("").strip().lower()
        if raw == "b":
            return
        elif raw == "a":
            console.print("  [yellow]Applying all hardening settings...[/yellow]")
            for label, hive, path, name, val in HARDENING_SETTINGS:
                set_reg_dword(hive, path, name, val)
            console.print("  [bold green]All hardening settings applied![/bold green]"); time.sleep(1)
        elif raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(HARDENING_SETTINGS):
                label, hive, path, name, val = HARDENING_SETTINGS[idx]
                cur = get_reg_dword(hive, path, name)
                new = val if cur != val else 0
                set_reg_dword(hive, path, name, new)
                console.print("  [green]Toggled.[/green]"); time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  FUN / ENTERTAINMENT
# ═══════════════════════════════════════════════════════════════════════════════
ASCII_FONTS = {
    'A': ["  █  ", " █ █ ", "█████", "█   █", "█   █"],
    'B': ["████ ", "█   █", "████ ", "█   █", "████ "],
    'C': [" ████", "█    ", "█    ", "█    ", " ████"],
    'D': ["████ ", "█   █", "█   █", "█   █", "████ "],
    'E': ["█████", "█    ", "████ ", "█    ", "█████"],
    'F': ["█████", "█    ", "████ ", "█    ", "█    "],
    'G': [" ████", "█    ", "█  ██", "█   █", " ████"],
    'H': ["█   █", "█   █", "█████", "█   █", "█   █"],
    'I': ["█████", "  █  ", "  █  ", "  █  ", "█████"],
    'J': ["█████", "    █", "    █", "█   █", " ███ "],
    'K': ["█   █", "█  █ ", "███  ", "█  █ ", "█   █"],
    'L': ["█    ", "█    ", "█    ", "█    ", "█████"],
    'M': ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    'N': ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    'O': [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    'P': ["████ ", "█   █", "████ ", "█    ", "█    "],
    'Q': [" ███ ", "█   █", "█ █ █", "█  █ ", " ██ █"],
    'R': ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    'S': [" ████", "█    ", " ███ ", "    █", "████ "],
    'T': ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    'U': ["█   █", "█   █", "█   █", "█   █", " ███ "],
    'V': ["█   █", "█   █", "█   █", " █ █ ", "  █  "],
    'W': ["█   █", "█   █", "█ █ █", "██ ██", "█   █"],
    'X': ["█   █", " █ █ ", "  █  ", " █ █ ", "█   █"],
    'Y': ["█   █", " █ █ ", "  █  ", "  █  ", "  █  "],
    'Z': ["█████", "   █ ", "  █  ", " █   ", "█████"],
    '0': [" ███ ", "█  ██", "█ █ █", "██  █", " ███ "],
    '1': ["  █  ", " ██  ", "  █  ", "  █  ", "█████"],
    '2': [" ███ ", "█   █", "  ██ ", " █   ", "█████"],
    '3': ["████ ", "    █", " ███ ", "    █", "████ "],
    '4': ["█   █", "█   █", "█████", "    █", "    █"],
    '5': ["█████", "█    ", "████ ", "    █", "████ "],
    '6': [" ████", "█    ", "████ ", "█   █", " ███ "],
    '7': ["█████", "    █", "   █ ", "  █  ", "  █  "],
    '8': [" ███ ", "█   █", " ███ ", "█   █", " ███ "],
    '9': [" ███ ", "█   █", " ████", "    █", "████ "],
    ' ': ["     ", "     ", "     ", "     ", "     "],
    '!': ["  █  ", "  █  ", "  █  ", "     ", "  █  "],
    '?': [" ███ ", "█   █", "  ██ ", "     ", "  █  "],
    '.': ["     ", "     ", "     ", "     ", "  █  "],
}

def ascii_art_generator():
    while True:
        header("ASCII Art Generator", "Convert text to large ASCII art")
        text = ask("Text to convert (or B)").strip().upper()
        if text in ("B", ""):
            return

        colors = ["red", "yellow", "green", "cyan", "blue", "magenta"]
        console.print()
        for row in range(5):
            line = ""
            for ch in text:
                if ch in ASCII_FONTS:
                    line += ASCII_FONTS[ch][row] + " "
                else:
                    line += "     " + " "
            color = colors[row % len(colors)]
            console.print(f"  [{color}]{line}[/{color}]")
        console.print()
        pause()


def matrix_rain():
    header("Matrix Rain", "Press ENTER to stop")
    console.print("  [dim]Press ENTER to stop[/dim]\n")
    stop = False
    def wait():
        nonlocal stop
        input()
        stop = True
    threading.Thread(target=wait, daemon=True).start()

    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 80
    drops = [random.randint(0, 20) for _ in range(cols)]
    chars = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789ABCDEF"

    with Live(console=console, refresh_per_second=8, screen=False) as live:
        while not stop:
            lines = []
            for _ in range(min(os.get_terminal_size().lines - 4, 30)):
                row = ""
                for c in range(min(cols, 120)):
                    if random.random() < 0.05:
                        row += f"[bold green]{random.choice(chars)}[/bold green]"
                    elif random.random() < 0.15:
                        row += f"[green]{random.choice(chars)}[/green]"
                    elif random.random() < 0.08:
                        row += f"[dim green]{random.choice(chars)}[/dim green]"
                    else:
                        row += " "
                lines.append(row)
            live.update(Text.from_markup("\n".join(lines)))
            time.sleep(0.1)
            if stop:
                break


def system_stats_flex():
    header("System Stats Flex", "Neofetch-style system overview")

    cpu = platform.processor()
    cpu_cores = psutil.cpu_count(logical=False)
    cpu_logic = psutil.cpu_count(logical=True)
    mem = psutil.virtual_memory()
    disk_total = sum(psutil.disk_usage(p.mountpoint).total for p in psutil.disk_partitions(all=False))
    disk_used = sum(psutil.disk_usage(p.mountpoint).used for p in psutil.disk_partitions(all=False))
    gpu = run_ps("(Get-WmiObject Win32_VideoController | Select-Object -First 1).Name")
    os_name = run_ps("(Get-WmiObject Win32_OperatingSystem).Caption")
    uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    shell = "PowerShell" if "powershell" in os.environ.get("PSModulePath", "").lower() else "CMD"

    art = [
        "[cyan]         ████████████         [/cyan]",
        "[cyan]      ████            ████     [/cyan]",
        "[cyan]    ██  ████████████████  ██   [/cyan]",
        "[cyan]   █  ██              ██  █   [/cyan]",
        "[cyan]  █  █  ████████████  █  █   [/cyan]",
        "[cyan]  █  █  █    ██    █  █  █    [/cyan]",
        "[cyan]  █  █  █    ██    █  █  █    [/cyan]",
        "[cyan]  █  █  ████████████  █  █    [/cyan]",
        "[cyan]   █  ██              ██  █   [/cyan]",
        "[cyan]    ██  ████████████████  ██   [/cyan]",
        "[cyan]      ████            ████     [/cyan]",
        "[cyan]         ████████████          [/cyan]",
    ]

    info_lines = [
        f"[bold cyan]{os.environ.get('USERNAME', '?')}[/bold cyan]@[bold cyan]{platform.node()}[/bold cyan]",
        f"[dim]{'─' * 30}[/dim]",
        f"[bold]OS:[/bold] {os_name}",
        f"[bold]Kernel:[/bold] {platform.version()}",
        f"[bold]Uptime:[/bold] {str(uptime).split('.')[0]}",
        f"[bold]Shell:[/bold] {shell}",
        f"[bold]CPU:[/bold] {cpu[:40]}",
        f"[bold]Cores:[/bold] {cpu_cores}/{cpu_logic} (phys/logical)",
        f"[bold]GPU:[/bold] {gpu[:40] if gpu else '?'}",
        f"[bold]RAM:[/bold] {fmt_bytes(mem.used)} / {fmt_bytes(mem.total)} ({mem.percent}%)",
        f"[bold]Disk:[/bold] {fmt_bytes(disk_used)} / {fmt_bytes(disk_total)}",
        "",
        "[on red]   [/on red][on green]   [/on green][on yellow]   [/on yellow][on blue]   [/on blue][on magenta]   [/on magenta][on cyan]   [/on cyan][on white]   [/on white]",
    ]

    max_lines = max(len(art), len(info_lines))
    console.print()
    for i in range(max_lines):
        left = art[i] if i < len(art) else " " * 30
        right = info_lines[i] if i < len(info_lines) else ""
        console.print(f"  {left}  {right}")
    console.print()
    pause()


def typing_speed_test():
    while True:
        header("Typing Speed Test", "Test your WPM")
        word_bank = [
            "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
            "python", "developer", "keyboard", "monitor", "system", "network",
            "performance", "security", "optimization", "terminal", "command",
            "process", "memory", "storage", "interface", "protocol", "database",
            "function", "variable", "algorithm", "framework", "debugging",
            "encryption", "bandwidth", "firewall", "operating", "hardware",
        ]

        words = [random.choice(word_bank) for _ in range(25)]
        target = " ".join(words)
        console.print(f"  [bold cyan]Type this text:[/bold cyan]\n")
        console.print(f"  [yellow]{target}[/yellow]\n")
        console.print("  [dim]Press ENTER when ready, then type the text and press ENTER again.[/dim]")
        input()

        start_time = time.time()
        typed = input("  > ").strip()
        elapsed = time.time() - start_time

        # Calculate WPM
        typed_words = typed.split()
        target_words = target.split()
        correct = sum(1 for a, b in zip(typed_words, target_words) if a == b)
        wpm = (len(typed_words) / elapsed) * 60
        accuracy = (correct / len(target_words)) * 100 if target_words else 0

        console.print(f"\n  [bold]Results:[/bold]")
        wpm_col = "green" if wpm >= 60 else "yellow" if wpm >= 30 else "red"
        acc_col = "green" if accuracy >= 90 else "yellow" if accuracy >= 70 else "red"
        console.print(f"  Speed:    [{wpm_col}]{wpm:.0f} WPM[/{wpm_col}]")
        console.print(f"  Accuracy: [{acc_col}]{accuracy:.0f}%[/{acc_col}]")
        console.print(f"  Time:     [cyan]{elapsed:.1f}s[/cyan]")
        console.print(f"  Words:    {correct}/{len(target_words)} correct")

        if not confirm("\n  Try again?"):
            return


def number_guessing_game():
    while True:
        header("Number Guessing Game")
        difficulty = numbered_menu(["Easy (1-50, 10 guesses)", "Medium (1-100, 7 guesses)", "Hard (1-500, 9 guesses)"])
        if difficulty == -1:
            return

        ranges = [(50, 10), (100, 7), (500, 9)]
        max_num, max_guesses = ranges[difficulty]
        target = random.randint(1, max_num)
        guesses = 0

        header("Number Guessing Game", f"Guess 1-{max_num} ({max_guesses} attempts)")
        while guesses < max_guesses:
            guess_str = ask(f"Guess ({max_guesses - guesses} left)").strip()
            if guess_str.lower() == "q":
                break
            if not guess_str.isdigit():
                continue
            guess = int(guess_str)
            guesses += 1

            if guess == target:
                console.print(f"\n  [bold green]Correct! You got it in {guesses} guesses![/bold green]")
                break
            elif guess < target:
                console.print(f"  [yellow]Higher![/yellow]")
            else:
                console.print(f"  [yellow]Lower![/yellow]")
        else:
            console.print(f"\n  [red]Out of guesses! The number was {target}.[/red]")

        if not confirm("\n  Play again?"):
            return


def rock_paper_scissors():
    score = {"wins": 0, "losses": 0, "ties": 0}
    while True:
        header("Rock Paper Scissors", f"Wins: {score['wins']}  Losses: {score['losses']}  Ties: {score['ties']}")
        opts = ["Rock", "Paper", "Scissors"]
        sel = numbered_menu(opts)
        if sel == -1:
            return

        player = opts[sel]
        computer = random.choice(opts)

        console.print(f"\n  You chose:      [cyan]{player}[/cyan]")
        console.print(f"  Computer chose: [yellow]{computer}[/yellow]\n")

        if player == computer:
            console.print("  [dim]It's a tie![/dim]")
            score["ties"] += 1
        elif (player == "Rock" and computer == "Scissors") or \
             (player == "Paper" and computer == "Rock") or \
             (player == "Scissors" and computer == "Paper"):
            console.print("  [bold green]You win![/bold green]")
            score["wins"] += 1
        else:
            console.print("  [bold red]You lose![/bold red]")
            score["losses"] += 1
        time.sleep(1)


TABS = {
    "tools": {
        "label": "Tools",
        "color": "cyan",
        "items": [
            ("Junk File Cleaner",        junk_cleaner),
            ("Process Manager",          process_manager),
            ("Startup Manager",          startup_manager),
            ("Network Tools",            network_tools),
            ("Background Services",      services_manager),
            ("Registry Cleaner",         registry_cleaner),
            ("Disk Optimizer",           disk_optimizer),
            ("System Repair",            system_repair),
            ("Event Log Viewer",         event_log_viewer),
            ("Environment Variables",    env_editor),
            ("Firewall & Open Ports",    firewall_viewer),
            ("Hash Checker & Passwords", hash_and_password),
            ("System Information",       system_info),
            ("Live Performance Monitor", live_monitor),
            ("Memory Optimizer",         memory_optimizer),
            ("Scheduled Tasks",          scheduled_tasks_viewer),
            ("Hosts File Editor",        hosts_file_editor),
            ("WiFi Manager",             wifi_manager),
            ("Installed Programs",       installed_programs),
            ("Disk Space Analyzer",      disk_space_analyzer),
            ("System Restore Manager",   system_restore_manager),
            ("Certificate Manager",      certificate_viewer),
            ("Temp File Monitor",        temp_file_monitor),
            ("Battery Health Report",    battery_health_report),
            ("Network Profile Manager",  network_profile_manager),
            ("Windows Feature Manager",  windows_feature_manager),
            ("Clipboard Manager",        clipboard_manager),
            ("Service Dependencies",     service_dependency_viewer),
            ("Bandwidth Monitor",        bandwidth_monitor),
            ("Network Mapper",           network_mapper),
            ("Visual Traceroute",        visual_traceroute),
            ("Ping Sweep",               ping_sweep),
            ("Wake on LAN",              wake_on_lan),
            ("Connection Monitor",       connection_monitor),
        ]
    },
    "optimize": {
        "label": "Optimize",
        "color": "yellow",
        "items": [
            ("Full Optimize  ", full_optimize),
            ("Power Plan Manager",         power_plan_manager),
            ("Game & Performance",         game_optimizer),
            ("Visual Effects",             visual_effects),
            ("CPU Priority Tweaks",        cpu_tweaks),
            ("GPU Optimization",           gpu_optimizer),
            ("SSD / HDD Tweaks",           storage_tweaks),
            ("Network Latency  (Gaming)",  network_latency_tweaks),
            ("Telemetry & Privacy",        telemetry_disabler),
            ("Hibernation & Sleep",        sleep_settings),
            ("Advanced Registry Tweaks",   advanced_registry_tweaks),
            ("Boot & Startup Analysis",    startup_profiler),
            ("Driver Health Check",        driver_health_check),
            ("Windows Defender Tuning",    windows_defender_tuner),
            ("Context Menu Cleanup",       context_menu_cleanup),
            ("DNS Optimizer",              dns_optimizer),
            ("RAM Optimizer",              ram_optimizer),
            ("Windows Update Manager",     windows_update_manager),
            ("Background Process Killer",  background_process_optimizer),
            ("Notification Disabler",      notification_disabler),
            ("Page File Optimizer",        page_file_optimizer),
            ("System Timer Resolution",    system_timer_resolution),
            ("USB Power Management",       usb_power_optimizer),
            ("Audio Latency Tweaks",       audio_latency_optimizer),
            ("Windows Search Optimizer",   windows_search_optimizer),
            ("Shader Cache Manager",       shader_cache_manager),
            ("Interrupt Affinity (MSI)",   interrupt_affinity_tool),
            ("Boot Config (BCDEdit)",      boot_config_tweaks),
            ("Windows Debloater v2",       windows_debloater_v2),
            ("SSD / HDD Health",           ssd_hdd_health),
            ("Startup Impact Analyzer",    startup_impact_analyzer),
            ("Memory Leak Detector",       memory_leak_detector),
            ("Windows Hardening",          windows_hardening),
        ]
    },
    "osint": {
        "label": "OSINT",
        "color": "magenta",
        "items": [
            ("IP / Domain Lookup",        ip_domain_lookup),
            ("DNS Record Lookup",         dns_lookup),
            ("Reverse IP Lookup",         reverse_ip_lookup),
            ("WHOIS & Domain Intel",      whois_domain_intel),
            ("Subdomain Finder",          subdomain_finder),
            ("Port Scanner",              port_scanner_advanced),
            ("Breach / Leak Checker",     breach_checker),
            ("Google Dorking Helper",     google_dorking),
            ("URL Analyzer",             url_analyzer),
            ("MAC Address Lookup",       mac_lookup),
            ("Tor/VPN/Proxy Detector",   tor_vpn_detector),
            ("Website Fingerprinter",    website_fingerprinter),
            ("Email Header Analyzer",    email_header_analyzer),
            ("EXIF / Image Metadata",    exif_extractor),
            ("Phone Number Lookup",      phone_lookup),
            ("SSL Certificate Checker",  ssl_checker),
            ("Geolocation Tracker",      geolocation_tracker),
            ("Shodan Search Helper",     shodan_search),
            ("IP Reputation Checker",    ip_reputation),
            ("Username Search",          username_search),
            ("Social Media Deep Scraper",social_media_scraper),
            ("Dark Web Mention Checker",darkweb_checker),
            ("HTTP Header Analyzer",    http_header_analyzer),
            ("Technology Detector",     technology_detector),
            ("Robots & Sitemap Viewer", robots_sitemap_viewer),
            ("Wayback Machine Checker", wayback_checker),
            ("Link Extractor",          link_extractor),
            ("Cert Transparency Search",cert_transparency_search),
            ("ASN Lookup",              asn_lookup),
            ("Domain Age Checker",      domain_age_checker),
            ("Reverse Image Search",    reverse_image_search),
            ("Favicon Hash Lookup",     favicon_hash_lookup),
        ]
    },
    "security": {
        "label": "Security",
        "color": "red",
        "items": [
            ("Hash Cracker",             hash_cracker),
            ("Directory Bruteforcer",    directory_bruteforcer),
            ("Subdomain Takeover Check", subdomain_takeover_check),
            ("Header Security Analyzer", header_security_analyzer),
            ("CVE Lookup",               cve_lookup),
            ("Privacy Audit",            privacy_audit),
            ("Tracker Blocker",          tracker_blocker),
            ("Browser Data Cleaner",     browser_data_cleaner),
            ("DNS Leak Test",            dns_leak_test),
            ("VPN Checker",              vpn_checker),
            ("Webcam & Mic Monitor",     webcam_mic_monitor),
        ]
    },
    "utilities": {
        "label": "Utilities",
        "color": "green",
        "items": [
            ("Text Utilities",           text_utilities),
            ("JSON Formatter",           json_formatter),
            ("Password Generator",       password_generator),
            ("Hash Generator",           hash_generator),
            ("Base Converter",           base_converter),
            ("Timestamp Converter",      timestamp_converter),
            ("Quick Calculator",         quick_calculator),
            ("Unit Converter",           unit_converter),
            ("File Search",              file_search_tool),
            ("Duplicate File Finder",    duplicate_file_finder),
            ("Bulk File Renamer",        bulk_file_renamer),
            ("Stopwatch & Timer",        stopwatch_timer),
            ("Color Picker / Converter", color_picker),
            ("Diff Tool",                diff_tool),
            ("Port Manager",             port_manager),
            ("File Watcher",             file_watcher),
            ("File Encryptor",           file_encryptor),
            ("Secure File Shredder",     secure_file_shredder),
            ("Archive Manager",          archive_manager),
            ("File Integrity Checker",   file_integrity_checker),
            ("Settings",                 settings_menu),
        ]
    },
    "fun": {
        "label": "Fun",
        "color": "bright_blue",
        "items": [
            ("ASCII Art Generator",      ascii_art_generator),
            ("Matrix Rain",              matrix_rain),
            ("System Stats Flex",        system_stats_flex),
            ("Typing Speed Test",        typing_speed_test),
            ("Number Guessing Game",     number_guessing_game),
            ("Rock Paper Scissors",      rock_paper_scissors),
        ]
    },
}

TAB_ORDER = ["tools", "optimize", "osint", "security", "utilities", "fun"]
def match_tab(text):
    """Match input to a tab name by substring, prefix, or single letter"""
    text = text.lower().strip()
    if not text: return None
    for key in TAB_ORDER:
        if text == key: return key           # exact match
    for key in TAB_ORDER:
        if key.startswith(text): return key  # prefix (t, to, osi, ut, etc.)
    for key in TAB_ORDER:
        if text in key: return key           # substring (ols, ize, int, ies, etc.)
    return None

def draw_tabs(active):
    parts = []
    for i, key in enumerate(TAB_ORDER):
        tab   = TABS[key]
        col   = tab["color"]
        label = tab["label"]
        cnt   = len(tab["items"])
        shortcut = key[0].upper()
        if key == active:
            parts.append(f"[bold {col} reverse]  {label} ({cnt})  [/bold {col} reverse]")
        else:
            parts.append(f"[dim]  {label} ({cnt})  [/dim]")
    nav = "[dim]< >[/dim]"
    return "  " + "  ".join(parts) + "  " + nav

def main():
    if platform.system() != "Windows":
        console.print("[red]Windows only.[/red]"); sys.exit(1)

    active_tab = "tools"

    while True:
        tab   = TABS[active_tab]
        items = tab["items"]
        col   = tab["color"]

        console.clear()
        adm = "[bold green] ADMIN [/bold green]" if IS_ADMIN else "[bold yellow] not admin [/bold yellow]"
        console.print(Panel(
            f"[bold cyan]raideds tool 🤑[/bold cyan]  {adm}\n"
            f"[dim]{platform.node()}  •  Windows {platform.version()[:30]}[/dim]",
            style="cyan", padding=(0,2)
        ))
        console.print(draw_tabs(active_tab))
        console.print(f"  [dim]{'─'*62}[/dim]\n")

        if len(items) > 14:
            cols = 3
            rows = (len(items) + cols - 1) // cols
            t = Table(box=box.SIMPLE, show_header=False, padding=(0,1), expand=False)
            for _ in range(cols):
                t.add_column("N",    style=f"bold {col}", width=4)
                t.add_column("Tool", style="white",        width=26)
            for r in range(rows):
                row_data = []
                for c in range(cols):
                    idx = r + c * rows
                    if idx < len(items):
                        star = "â­" if is_favorite(items[idx][0].strip()) else " "
                        row_data += [str(idx+1), f"{star} {items[idx][0]}"]
                    else:
                        row_data += ["",""]
                t.add_row(*row_data)
        else:
            cols = 2
            mid  = (len(items)+1)//2
            t = Table(box=box.SIMPLE, show_header=False, padding=(0,1), expand=False)
            t.add_column("N",    style=f"bold {col}", width=4)
            t.add_column("Tool", style="white",        width=30)
            t.add_column("N",    style=f"bold {col}", width=4)
            t.add_column("Tool", style="white",        width=30)
            for i in range(mid):
                l    = items[i]
                r2   = items[i+mid] if (i+mid) < len(items) else ("","")
                lnum = str(i+1)
                rnum = str(i+mid+1) if r2[0] else ""
                lstar = "â­" if is_favorite(l[0].strip()) else " "
                rstar = "â­" if r2[0] and is_favorite(r2[0].strip()) else " "
                t.add_row(lnum, f"{lstar} {l[0]}", rnum, f"{rstar} {r2[0]}" if r2[0] else "")

        console.print(t)
        console.print(f"\n  [bold {col}] 0[/bold {col}]  [dim]Quit[/dim]   [bold {col}]/[/bold {col}] [dim]Search[/dim]   [bold {col}]F[/bold {col}] [dim]Favorites[/dim]\n")

        raw = ask("Pick").strip().lower()
        if raw in ("0","q"):
            console.clear(); console.print("[bold cyan]Bye![/bold cyan]\n"); break
        elif raw == "/":
            search_tools_menu()
        elif raw == "f":
            # Show favorites menu
            favs = CONFIG.get("favorites", [])
            if not favs:
                console.print("\n  [yellow]No favorites yet! Use 'f<number>' to toggle favorites.[/yellow]")
                pause()
            else:
                console.print(f"\n  [bold cyan]â­ Favorites[/bold cyan]")
                fav_items = []
                for fav_name in favs:
                    for tab_key in TAB_ORDER:
                        for name, func in TABS[tab_key]["items"]:
                            if name.strip() == fav_name:
                                fav_items.append((name, func))
                                break
                if fav_items:
                    for i, (name, _) in enumerate(fav_items, 1):
                        console.print(f"    [cyan]{i}[/cyan]  {name}")
                    console.print(f"    [dim]0  Back[/dim]")
                    pick = ask("Pick favorite").strip()
                    if pick.isdigit() and 0 < int(pick) <= len(fav_items):
                        try:
                            add_recent(fav_items[int(pick)-1][0].strip())
                            fav_items[int(pick)-1][1]()
                        except KeyboardInterrupt: pass
                        except Exception as e:
                            console.print(f"\n  [red]Error: {e}[/red]")
                            pause()
                else:
                    console.print("  [yellow]Favorites not found in current tools.[/yellow]")
                    pause()
        elif raw.startswith("f") and raw[1:].isdigit():
            # Toggle favorite for tool number
            n = int(raw[1:]) - 1
            if 0 <= n < len(items):
                tool_name = items[n][0].strip()
                toggle_favorite(tool_name)
                star = "â­ Added to" if is_favorite(tool_name) else "Removed from"
                console.print(f"\n  [cyan]{star} favorites: {tool_name}[/cyan]")
                time.sleep(0.8)
        elif raw == "tab" or raw == ">":
            idx = TAB_ORDER.index(active_tab)
            active_tab = TAB_ORDER[(idx+1) % len(TAB_ORDER)]
        elif raw == "<":
            idx = TAB_ORDER.index(active_tab)
            active_tab = TAB_ORDER[(idx-1) % len(TAB_ORDER)]
        elif match_tab(raw):
            active_tab = match_tab(raw)
        elif raw.isdigit():
            n = int(raw) - 1
            if 0 <= n < len(items):
                try:
                    tool_name = items[n][0].strip()
                    add_recent(tool_name)
                    items[n][1]()
                except KeyboardInterrupt: pass
                except Exception as e:
                    console.print(f"\n  [red]Error: {e}[/red]")
                    import traceback; traceback.print_exc()
                    pause()


def request_admin_at_startup():
    """Prompt user for admin privileges at startup"""
    if IS_ADMIN:
        console.print("[green]✓ Running with Administrator privileges[/green]\n")
        return
    
    console.print("[bold cyan]┌─ Administrator Privileges ─┐[/bold cyan]")
    console.print("[dim]This tool works better with admin access (Registry tweaks, etc.)[/dim]")
    
    if confirm("Request Administrator privileges?"):
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1)
            sys.exit(0)  # Exit current non-admin process
        except Exception as e:
            console.print(f"[red]Could not elevate privileges: {e}[/red]")
            console.print("[yellow]Continuing in normal mode...[/yellow]\n")
            time.sleep(1)
    else:
        console.print("[yellow]Continuing in normal user mode...[/yellow]\n")
        time.sleep(0.5)

if __name__ == "__main__":
    request_admin_at_startup()
    main()
