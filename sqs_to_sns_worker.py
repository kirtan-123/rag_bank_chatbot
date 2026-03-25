import argparse
import time

from aws_notifications import process_login_events_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Process login events from SQS and send SNS emails")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds")
    args = parser.parse_args()

    while True:
        result = process_login_events_once()
        processed = result.get("processed", 0)
        reason = result.get("reason")

        if reason:
            print(f"Worker idle: {reason}")
        elif processed:
            print(f"Processed {processed} login event(s)")

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
