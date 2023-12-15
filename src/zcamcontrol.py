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
import json
import re
import pandas as pd

FUNC_CHOICES = {
    "help": "show help options",
    "list": "list videos. Optional argument: folder",
    "delete": "delete video. Argument: filepath",
    "pull": "pull video, '-1' as source arg pulls last capture. Arguments: source [destination]",
    "info": "info",
    "start": "start recording",
    "stop": "stop recording",
    "preview": "preview",
    "get": """
            Retrive a value from the camera. Partial match is allowed. An area can also be matched. 
            Multiple values can be retrieved by using a comma separated list.
            If the options '--csv filename' is set the output will be written to a csv file.
            With no key all settings will be retrieved.
            Argument: key
            """,
    "set": """
            Set a value. Partial match is allowed. An area can also be matched.
            If the options '--csv filename' is set the values will be set according to the csv file.
            Optional argument: key value
            """,
    "date": "date",
    "keys": """
            Search for keys. Partial match allowed. 
            If no keys are set all keys and areas will be listed.
            """,
}
default_values = {"debug": 0, "func": "help"}

IP = None
KEYS = None
QUIET = False


def is_file(filename):
    if pathlib.Path(filename).suffix == "":
        return False
    return True


def run_query(path, action="", debug=0):
    global IP
    # no '/' in the beginning
    if path[0] == "/":
        path = path[1:]
    try:
        query = f"http://{IP}/{path}{action}"
        if debug > 0:
            print(f"run {query}")
        resp = requests.get(query)
        if debug > 0:
            print(f"response {resp}")
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


def list_path(path, files, folders, debug=0):
    if path[-1] != "/":
        path = f"{path}/"
    _folders = run_query(path, debug=debug).json()
    for file in _folders["files"]:
        # check ending (can we do better?)
        long = f"{path}{file}"
        if is_file(long):
            files.append(long)
        else:
            folders.append(long)
            list_path(long, files, folders, debug=debug)

    return


def list_videos(folder, debug=0):
    _folder = "DCIM"
    if folder is not None:
        _folder = f"{_folder}/{folder}"
    # TODO filter stray '/'
    files = []
    folders = []
    list_path(_folder, files, folders, debug=debug)
    for file in files:
        print(file)


def delete_video(filename, debug=0):
    # either filename or all
    # match wildcard '*'
    if filename[-1] == "*":
        folders = []
        files = []
        list_path("DCIM", files, folders)
        for file in files:
            if file.startswith(filename[:-1]):
                # good to know what you just destroyed :)
                print(f"delete {file}")
                delete_video(file, debug=debug)
    else:
        run_query(filename, "?act=rm", debug=debug)


def pull_video(source, destination, debug=0):
    if source == "-1":
        # check latest file
        source = query("last_file_name", debug=debug)
    if destination == ".":
        destination = os.path.basename(source)
    file = run_query(source, debug=debug)
    if file is None:
        print(f"{source} not found")
        return

    with open(destination, "wb") as f:
        f.write(file.content)


def start(debug=0):
    # first make sure we are in rec mode.
    run_query("ctrl/mode", "?action=to_rec", debug=debug)
    run_query("ctrl/rec", "?action=start", debug=debug)
    return


def stop(debug=0):
    run_query("ctrl/rec", "?action=stop", debug=debug)
    return


def find_key(key, multi=False, multiwarn=True):
    # look for exct first
    lkey = KEYS.loc[KEYS["key"] == key]
    skey = None
    if len(lkey) > 0:
        # exact match
        skey = [lkey.values[0][0]]
    lkey = KEYS.loc[
        (KEYS["key"].str.contains(key, case=False))
        | (KEYS["area"].str.contains(key, case=False))
    ]

    if len(lkey) > 1:
        if not QUIET and multiwarn:
            print(f"\nmultiple keys found for {key}\n")
            print_settings(lkey)
        if multi:
            skey = lkey["key"].values
        elif skey is None or len(skey) == 0:
            return None
        elif not QUIET:
            print(f'\nMatching "{skey}"')
    return skey


def get(key, multi=False, debug=0, multiwarn=True):
    # allow for a comma separated list
    skey = []
    keys = key.split(",")
    for key in keys:
        skey_ = find_key(key.strip(), multi=multi, multiwarn=multiwarn)
        if skey_ is not None:
            skey.extend(skey_)
    if skey is not None:
        ret = {}
        for k in skey:
            data = run_query("ctrl/get", f"?k={k}", debug=debug).json()
            if int(data["code"]) == 0:
                ret[k] = data["value"]
            else:
                print(f"ERROR: {k} could not be retrieved")
        return ret
    return None


def set(key, value, debug=0):
    skey = find_key(key)[0]
    if skey != None:
        run_query("ctrl/set", f"?{skey}={value}", debug=debug)
    return


def get_info(debug=0):
    data = run_query("/info", "", debug=debug).json()
    if debug > 0:
        print(f" {json.dumps(data, indent=2)}")
    return data


def print_info(info):
    print(f" {json.dumps(info, indent=2)}")


def set_date(date, debug=0):
    set_date = ""
    if date is not None and len(date) > 0:
        # YYYY-MM-DD:hh:mm:ss
        set_date = f"{date[0:10]}&time={date[11:19]}"
    else:
        now = datetime.datetime.now()
        if debug > 0:
            print(f"set date to {now}")
        year = now.year
        month = now.month
        hour = now.hour
        minutes = now.minute
        seconds = now.second
        set_date = f"{year}-{month}-{now.day}&time={hour}:{minutes}:{seconds}"

    run_query("datetime", f"?date={set_date}", debug=debug)


def print_settings(settings):
    for key in settings["key"]:
        single = settings[settings["key"] == key]
        if len(single.values) > 0:
            descr = single["description"].values[0]
            type = f"<{single['type'].values[0]}>"
            print(f"{key.ljust(20,' ')} {type.ljust(20,' ')} {descr}")


def print_key_info(text):
    # sort and print
    if len(text) > 1:
        # First areas
        areas = (
            KEYS.loc[KEYS["area"].str.contains(text, case=False)][["area"]]
            .drop_duplicates()
            .values[:, 0]
        )
        if len(areas) > 0:
            print(f"Areas: {', '.join(areas)}\n\n")
            for area in areas:
                print(f"{area}:")
                filt = KEYS[KEYS["area"] == area].sort_values(by=["key"])
                if len(filt) > 0:
                    print_settings(filt)
                print("\n\n-------\n")
        # individual fields
        fields = KEYS.loc[KEYS["key"].str.contains(text, case=False)]
        if len(fields) > 0:
            print("Keys:\n")

            fields = fields.sort_values(by=["key"])
            if len(fields):
                print_settings(fields)

            print("\n\n-------\n")


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
        "-q",
        "--quiet",
        action="store_true",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="export/input settings from csv file",
    )
    parser.add_argument(
        "-m",
        "--multi",
        action="store_true",
        help="allow multiple keys to be retrieved if key match several",
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


def parse_keys(path):
    syspath = sys.path[0]

    # parse the keys
    regex = r"^(?P<key>[\w]*)\s*(?P<type>[\w]*)\s*(?P<description>[\w\s\-\/]*)"

    current_area = ""
    keys = []
    with open(f"{syspath}/{path}") as keyfile:
        lines = keyfile.readlines()
        for line in lines:
            match = re.match(regex, line)
            if match:
                key = match.group("key").strip()
                type = match.group("type").strip()
                description = match.group("description").strip()

                if type == "type":
                    continue
                elif len(type) == 0:
                    current_area = key
                else:
                    keys.append(
                        {
                            "key": key,
                            "type": type,
                            "description": description,
                            "area": current_area,
                        }
                    )

    return pd.DataFrame(keys)


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

    global IP, KEYS, QUIET
    IP = options.ip
    KEYS = parse_keys("query_keys.txt")

    if options.quiet:
        QUIET = True
    # do something
    try:
        if len(options.func) > 1 and options.func[1] == "help":
            print(f"{FUNC_CHOICES[options.func[0]]}")
            sys.exit(1)

        if options.func[0] == "list":
            folder = ""
            if len(options.func) > 1:
                folder = options.func[1]
            list_videos(folder, options.debug)
        elif options.func[0] == "delete":
            filename = ""
            if len(options.func) > 1:
                filename = options.func[1]
            delete_video(filename, options.debug)
        elif options.func[0] == "pull":
            source = ""
            destination = "."
            if len(options.func) > 1:
                source = options.func[1]
                if len(options.func) > 2:
                    destination = options.func[2]
            else:
                print("Usage: pull source [destination]")
                exit(-1)
            pull_video(source, destination, options.debug)
        elif options.func[0] == "info":
            resp = get_info(debug=options.debug)
            print_info(resp)
        elif options.func[0] == "start":
            start()
        elif options.func[0] == "stop":
            stop()
        elif options.func[0] == "preview":
            webbrowser.open(f"http://{IP}/www/html/controller.html")
        elif options.func[0] == "get":
            if len(options.func) > 1:
                multi = len(options.csv) > 0 or options.multi

                result = get(options.func[1], multi=multi, debug=options.debug)
                if result is not None:
                    if len(options.csv) > 0:
                        # transpose
                        trans = [[key, result[key]] for key in result.keys()]
                        df = pd.DataFrame.from_dict(trans, orient="columns")
                        df.columns = ["key", "value"]
                        df.to_csv(options.csv, index=False)
                    for key in result:
                        print(f"{key}: {result[key]}")
            else:
                # get all settings
                areas = ", ".join(KEYS["area"].unique())
                result = get(areas, multi=True, multiwarn=False, debug=options.debug)
                if result is not None:
                    if len(options.csv) > 0:
                        # transpose
                        trans = [[key, result[key]] for key in result.keys()]
                        df = pd.DataFrame.from_dict(trans, orient="columns")
                        df.columns = ["key", "value"]
                        df.to_csv(options.csv, index=False)
                    for key in result:
                        print(f"{key}: {result[key]}")
        elif options.func[0] == "set":
            if len(options.func) > 2:
                key = options.func[1]
                val = options.func[2]
                set(key, val, options.debug)
                result = get(key, options.debug)
                if result[key] is not None:
                    if result[key].strip("'") != val:
                        print(f"Error setting {key} to {val}")
                else:
                    print(f"Error setting {key} to {val}")
            elif len(options.csv) > 0:
                # update settings from csv file
                df = pd.read_csv(options.csv)
                for key in df["key"]:
                    set(key, df[df["key"] == key]["value"].values[0], options.debug)

        elif options.func[0] == "date":
            date = ""
            if len(options.func) > 1:
                date = options.func[1]
            set_date(date, options.debug)
        elif options.func[0] == "keys":
            # special
            searchstring = ""
            if len(options.func) < 2:
                searchstring = ", ".join(KEYS["area"].unique())
                print(searchstring)
            else:
                searchstring = options.func[1]
            split = searchstring.split(",")
            for s in split:
                print_key_info(s.strip())
        else:
            print("unknown function")
            sys.exit(1)
    except Exception as e:
        print(f"{options.func} failed: {e}")


if __name__ == "__main__":
    main(sys.argv)
