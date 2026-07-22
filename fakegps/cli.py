"""Command-line interface for FakeGPS."""

import sys
import argparse

from .core import list_connected_devices, set_location, clear_location, play_gpx_file, check_tunneld_running, run_async
from .places import get_place, add_place, remove_place, list_places, BUILTIN_PLACES
from .coords import gcj02_to_wgs84


def _print_devices():
    try:
        devices = run_async(list_connected_devices())
    except Exception as e:
        print(f"Error: {e}")
        return []
    if not devices:
        print("No devices found. Connect iPhone via USB and trust this computer.")
        return []
    print(f"Found {len(devices)} device(s):")
    for d in devices:
        print(f"  {d.name} (iOS {d.ios_version})")
    return devices


def _print_places():
    places = list_places()
    print("Built-in places:")
    for name in BUILTIN_PLACES:
        lat, lng, label = BUILTIN_PLACES[name]
        print(f"  {name:12s} {label:16s} ({lat}, {lng})")
    custom = {k: v for k, v in places.items() if k not in BUILTIN_PLACES}
    if custom:
        print("\nCustom places:")
        for name, (lat, lng, label) in custom.items():
            print(f"  {name:12s} ({lat}, {lng})")


def _do_set(lat, lng):
    if not check_tunneld_running():
        print("Warning: tunneld not running. For iOS 17+, start it in another terminal:")
        print("  sudo python3 -m pymobiledevice3 remote tunneld")
    print(f"Setting location: {lat}, {lng}")
    try:
        result = run_async(set_location(lat, lng))
        print(f"Location set to ({lat}, {lng}). Press Ctrl+C to restore.")
        # Hold until interrupted
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nRestoring real location...")
            run_async(clear_location())
            print("Done.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def _do_clear():
    print("Restoring real location...")
    try:
        run_async(clear_location())
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def _do_place(name):
    place = get_place(name)
    if place is None:
        print(f"Unknown place: {name}")
        print("Use 'fakegps /places' to list available places.")
        sys.exit(1)
    lat, lng, label = place
    print(f"Going to: {label} ({lat}, {lng})")
    _do_set(lat, lng)


def interactive_mode():
    """Interactive REPL mode."""
    print("FakeGPS v6.2.6 - iPhone Virtual Location Tool")
    print("Type 'help' for commands, 'exit' to quit.\n")
    _print_places()
    print()

    while True:
        try:
            line = input("fakegps> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not line:
            continue

        # Strip leading /
        if line.startswith("/"):
            line = line[1:]

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit", "q"):
            print("Exiting.")
            break
        elif cmd in ("help", "h"):
            _print_help()
        elif cmd == "gui":
            _open_gui()
        elif cmd == "list":
            _print_devices()
        elif cmd == "places":
            _print_places()
        elif cmd == "set":
            if len(args) < 2:
                print("Usage: /set <lat> <lng>")
                continue
            try:
                lat, lng = float(args[0]), float(args[1])
            except ValueError:
                print("Invalid coordinates.")
                continue
            _do_set(lat, lng)
        elif cmd == "clear":
            _do_clear()
        elif cmd == "map":
            _open_gui()
        elif cmd == "add":
            if len(args) < 3:
                print("Usage: /add <name> <lat> <lng>")
                continue
            name = args[0]
            try:
                lat, lng = float(args[1]), float(args[2])
            except ValueError:
                print("Invalid coordinates.")
                continue
            add_place(name, lat, lng, is_gcj02=True)
            print(f"Added: {name}")
        elif cmd == "remove":
            if not args:
                print("Usage: /remove <name>")
                continue
            if remove_place(args[0]):
                print(f"Removed: {args[0]}")
            else:
                print(f"Not found: {args[0]}")
        elif cmd == "play":
            if not args:
                print("Usage: /play <file.gpx>")
                continue
            print(f"Playing GPX: {args[0]}")
            try:
                run_async(play_gpx_file(args[0]))
                print("GPX playback finished.")
            except Exception as e:
                print(f"Error: {e}")
        else:
            # Try as a place name
            place = get_place(cmd)
            if place:
                lat, lng, label = place
                print(f"Going to: {label} ({lat}, {lng})")
                _do_set(lat, lng)
            else:
                print(f"Unknown command: {cmd}. Type 'help' for commands.")


def _open_gui():
    """Launch GUI from CLI."""
    try:
        from .gui import main as gui_main
        gui_main()
    except ImportError:
        print("GUI not available. Install pywebview: pip install pywebview")


def _print_help():
    print("""
Commands:
  <place>              Go to built-in or custom place
  /set <lat> <lng>     Set location to coordinates
  /gui, /map           Open GUI map
  /clear               Restore real location
  /list                List connected devices
  /places              List all places
  /add <n> <lat> <lng> Add custom place
  /remove <name>       Remove custom place
  /play <file.gpx>     Play GPX trajectory
  /help                Show this help
  /exit                Exit

Built-in places: tiananmen, guomao, birdnest, shanghai, guangzhou,
                 paris, newyork, tokyo, london, rome
""")


def main():
    parser = argparse.ArgumentParser(
        prog="fakegps",
        description="FakeGPS v6.2.6 - iPhone Virtual Location Tool (cross-platform)"
    )
    parser.add_argument("command", nargs="?", help="Place name or command (set, clear, list, places, map, play, add, remove)")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--gui", action="store_true", help="Force GUI mode")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode")

    # Parse known args to support both modes
    args, unknown = parser.parse_known_args()

    # If --gui explicitly, launch GUI
    if args.gui:
        _open_gui()
        return

    # If no command at all and not --cli, try GUI first
    if args.command is None and not args.cli:
        try:
            import webview
            _open_gui()
            return
        except ImportError:
            # No GUI available, fall through to interactive mode
            interactive_mode()
            return

    # If command is "map", open GUI
    if args.command == "map":
        _open_gui()
        return

    # CLI mode with subcommand
    if args.command:
        cmd = args.command.lstrip("/")
        all_args = args.args + unknown

        if cmd in ("set",):
            if len(all_args) < 2:
                print("Usage: fakegps set <lat> <lng>")
                sys.exit(1)
            _do_set(float(all_args[0]), float(all_args[1]))
        elif cmd in ("clear",):
            _do_clear()
        elif cmd in ("list",):
            _print_devices()
        elif cmd in ("places",):
            _print_places()
        elif cmd in ("add",):
            if len(all_args) < 3:
                print("Usage: fakegps add <name> <lat> <lng>")
                sys.exit(1)
            add_place(all_args[0], float(all_args[1]), float(all_args[2]), is_gcj02=True)
            print(f"Added: {all_args[0]}")
        elif cmd in ("remove",):
            if not all_args:
                print("Usage: fakegps remove <name>")
                sys.exit(1)
            if remove_place(all_args[0]):
                print(f"Removed: {all_args[0]}")
            else:
                print(f"Not found: {all_args[0]}")
        elif cmd in ("play",):
            if not all_args:
                print("Usage: fakegps play <file.gpx>")
                sys.exit(1)
            run_async(play_gpx_file(all_args[0]))
        elif cmd in ("help", "--help", "-h"):
            _print_help()
        else:
            # Try as a place name
            _do_place(cmd)
        return

    # Interactive mode
    interactive_mode()
