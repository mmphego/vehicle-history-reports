#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys

from vehicle_history_reports import VehicleHistoryReports


def main():
    parser = argparse.ArgumentParser(
        description="Web scrapping tool for Vehicle information by VIN number"
    )
    parser.add_argument(
        "--vin-numbers",
        "-v",
        dest="vin_numbers",
        default=[],
        required=True,
        type=str,
        nargs="+",
        help="A list of VIN numbers.",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Do not open browser in headless mode.",
    )
    parser.add_argument(
        "--no-json-output",
        "-j",
        dest="no_json",
        action="store_false",
        help="Output as json.",
    )
    parser.add_argument("--host", dest="host", help="Proxy address. [Optional]")
    parser.add_argument("--port", dest="port", help="Proxy port. [Optional]")
    parser.add_argument(
        "--username", dest="username", help="Username to access proxy. [Optional]"
    )
    parser.add_argument(
        "--password", dest="password", help="Password to access proxy. [Optional]"
    )
    parser.add_argument(
        "--loglevel",
        dest="log_level",
        default="INFO",
        help="log level to use, default [INFO], options [INFO, DEBUG, ERROR]",
    )
    args = vars(parser.parse_args())
    data = []

    try:
        for vin_number in args.get("vin_numbers", [None]):
            if not vin_number:
                raise RuntimeError("Missing VIN Number.")
            vin_decoder = VehicleHistoryReports(vin_number=vin_number, **args)
            vin_decoder.open_site(headless=args.get("headless"))
            vin_decoder.navigate_site()
            vin_decoder.get_vehicle_details()
            vin_decoder.get_recent_recalls()
            vin_decoder.get_recent_complaints()
            vin_decoder.get_image_links()
            data.append(vin_decoder.data_structure)
            vin_decoder.close_session()
    except Exception as err:
        print(err)
        vin_decoder.close_session()
    finally:
        return json.dumps(data, indent=4, sort_keys=True) if args.get("no_json") else data


if __name__ == "__main__":
    test = main()
    print(test)
