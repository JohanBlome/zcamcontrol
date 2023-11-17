#!/usr/bin/env python3

"""zcamcontrol.py module description."""

import sys
import argparse
import requests
import webbrowser
import os.path
import pathlib
import datetime
import calendar

FUNC_CHOICES = {
    "help": "show help options",
    "list": "list videos. Optional argument: folder",
    "delete": "delete video. Argument: filepath",
    "download": "download video. Arguments: source [destination]",
    "info": "info",
    "start": "start recording",
    "stop": "stop recording",
    "preview": "preview",
    "query": "query",
    "date": "date",
}
default_values = {"debug": 0, "func": "help"}

IP = None


def is_file(filename):
    if pathlib.Path(filename).suffix == "":
        return False
    return True


def run_query(path, action="", debug=0):
    global IP
    try:
        query = f"http://{IP}/{path}{action}"
        if debug > 0:
            print(f"run {query}")
        resp = requests.get(query)
        if resp.status_code == 200:
            return resp
        else:
            print(f"error {resp.status_code}")

    except requests.exceptions.HTTPError as errh:
        print(errh)
    except requests.exceptions.ConnectionError as errc:
        print(errc)
    except requests.exceptions.Timeout as errt:
        print(errt)
    except requests.exceptions.RequestException as err:
        print(err)
    raise Exception("Error in run_query")


def list_path(path, files, folders):
    if path[-1] != "/":
        path = f"{path}/"
    _folders = run_query(path).json()
    for file in _folders["files"]:
        # check ending (can we do better?)
        long = f"{path}{file}"
        if is_file(long):
            files.append(long)
        else:
            folders.append(long)
            list_path(long, files, folders)

    return


def list_videos(folder):
    _folder = "DCIM"
    if folder is not None:
        _folder = f"{_folder}/{folder}"
    # TODO filter stray '/'
    files = []
    folders = []
    list_path(_folder, files, folders)
    for file in files:
        print(file)


def delete_video(filename):
    # either filename or all
    # match wildcard '*'
    if filename[-1] == "*":
        folders = []
        files = []
        list_path("DCIM", files, folders)
        for file in files:
            if file.startswith(filename[:-1]):
                print(f"delete {file}")
                delete_video(file)
    else:
        run_query(filename, "?act=rm")


def download_video(source, destination):
    if destination == ".":
        destination = os.path.basename(source)
    file = run_query(source)
    if file is None:
        print(f"{source} not found")
        return

    with open(destination, "wb") as f:
        f.write(file.content)


def start():
    run_query("ctrl/rec", "?action=start", debug=1)
    return


def stop():
    run_query("ctrl/rec", "?action=stop", debug=1)
    return


def query(key):
    data = run_query("ctrl/get", f"?k={key}", debug=1).json()
    print(f"{data['value']}")
    return


def set_date(date):
    set_date = ""
    if date is not None and len(date) > 0:
        # YYYY-MM-DD:hh:mm:ss
        set_date = f"{date[0:10]}&time={date[11:19]}"
    else:
        now = datetime.datetime.now()
        print(f"set date to {now}")
        year = now.year
        month = now.month
        hour = now.hour
        minutes = now.minute
        seconds = now.second
        set_date = f"{year}-{month}-{now.day}&time={hour}:{minutes}:{seconds}"

    run_query("datetime", f"?date={set_date}", debug=1)


def get_options(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "func",
        type=str,
        nargs="*",
        default=default_values["func"],
        # choices=FUNC_CHOICES.keys(),
        help="function followed by 'help' more info. Functions: %s"
        % (" | ".join("{}".format(k) for k, v in FUNC_CHOICES.items())),
    )

    parser.add_argument(
        "-ip",
        type=str,
        help="IP address of the camera",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="count",
        dest="debug",
        default=default_values["debug"],
        help="Increase verbosity (use multiple times for more)",
    )
    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        help="filename",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="output filename",
    )

    # do the parsing
    options = parser.parse_args(argv[1:])
    # implement help
    if options.func == "help":
        parser.print_help()
        sys.exit(0)

    if len(options.func) > 0 and options.func[0] not in FUNC_CHOICES.keys():
        print("unknown function")
        parser.print_help()
        sys.exit(1)

    return options


def main(argv):
    """
    Calculate stats for videos based on parsing individual frames
    with ffprobe frame parser.
    Can output data for a single file or aggregated data for several files.
    """

    options = get_options(argv)

    # print results
    if options.debug > 2:
        print(options)

    global IP
    IP = options.ip
    # do something
    try:
        if len(options.func) > 1 and options.func[1] == "help":
            print(f"{FUNC_CHOICES[options.func[0]]}")
            sys.exit(1)

        if options.func[0] == "list":
            folder = ""
            if len(options.func) > 1:
                folder = options.func[1]
            list_videos(folder)
        elif options.func[0] == "delete":
            filename = ""
            if len(options.func) > 1:
                filename = options.func[1]
            delete_video(filename)
        elif options.func[0] == "download":
            source = ""
            destination = "."
            if len(options.func) > 1:
                source = options.func[1]
                if len(options.func) > 2:
                    destination = options.func[2]
            else:
                print("Usage: download source [destination]")
                exit(-1)
            print("Call download......")
            download_video(source, destination)
        elif options.func[0] == "info":
            print("info")
        elif options.func[0] == "start":
            start()
        elif options.func[0] == "stop":
            stop()
        elif options.func[0] == "preview":
            webbrowser.open(f"http://{IP}/www/html/controller.html")
        elif options.func[0] == "query":
            if len(options.func) > 1:
                query(options.func[1])
        elif options.func[0] == "date":
            date = ""
            if len(options.func) > 1:
                date = options.func[1]
            set_date(date)
        else:
            print("unknown function")
            sys.exit(1)
    except Exception as e:
        print(f"{options.func} failed: {e}")


if __name__ == "__main__":
    main(sys.argv)
