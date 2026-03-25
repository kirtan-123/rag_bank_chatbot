import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None


load_dotenv()


def _get_region() -> str:
    return os.getenv("AWS_REGION", "ap-south-1")


def _get_queue_url() -> str:
    queue_url = os.getenv("SQS_LOGIN_QUEUE_URL", "").strip()
    if queue_url:
        return queue_url

    queue_arn = os.getenv("SQS_LOGIN_QUEUE_ARN", "").strip()
    if not queue_arn or boto3 is None:
        return ""

    # ARN format: arn:aws:sqs:<region>:<account-id>:<queue-name>
    arn_parts = queue_arn.split(":")
    if len(arn_parts) < 6:
        return ""

    queue_name = arn_parts[5]
    if not queue_name:
        return ""

    sqs = boto3.client("sqs", region_name=_get_region())
    try:
        response = sqs.get_queue_url(QueueName=queue_name)
        return response.get("QueueUrl", "")
    except Exception:
        return ""


def _get_topic_arn() -> str:
    return os.getenv("SNS_LOGIN_TOPIC_ARN", "").strip()


def _is_ready_for_enqueue() -> bool:
    return boto3 is not None and bool(_get_queue_url())


def _is_ready_for_publish() -> bool:
    return boto3 is not None and bool(_get_topic_arn())


def enqueue_login_event(user_name: str, account_type: str | None) -> dict:
    if not _is_ready_for_enqueue():
        return {
            "queued": False,
            "reason": "SQS not configured or boto3 missing",
        }

    try:
        sqs = boto3.client("sqs", region_name=_get_region())
        payload = {
            "event": "user_login",
            "user_name": user_name,
            "account_type": account_type,
            "logged_in_at": datetime.now(timezone.utc).isoformat(),
        }

        sqs.send_message(
            QueueUrl=_get_queue_url(),
            MessageBody=json.dumps(payload),
        )
    except Exception as exc:
        return {
            "queued": False,
            "reason": f"Failed to enqueue login notification: {exc}",
        }

    return {"queued": True}


def _extract_login_event(message_body: str) -> dict | None:
    try:
        payload = json.loads(message_body or "{}")
    except json.JSONDecodeError:
        return None

    # If this queue ever receives SNS-wrapped messages, unwrap them.
    if isinstance(payload, dict) and "Message" in payload and isinstance(payload["Message"], str):
        try:
            payload = json.loads(payload["Message"])
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None

    if payload.get("event") != "user_login":
        return None

    user_name = str(payload.get("user_name", "")).strip()
    account_type = str(payload.get("account_type", "")).strip()
    logged_in_at = str(payload.get("logged_in_at", "")).strip()

    if not user_name or not account_type or not logged_in_at:
        return None

    return {
        "user_name": user_name,
        "account_type": account_type,
        "logged_in_at": logged_in_at,
    }


def process_login_events_once(max_messages: int = 10, wait_time_seconds: int = 5) -> dict:
    if not _is_ready_for_enqueue() or not _is_ready_for_publish():
        return {
            "processed": 0,
            "reason": "SQS/SNS not configured or boto3 missing",
        }

    sqs = boto3.client("sqs", region_name=_get_region())
    sns = boto3.client("sns", region_name=_get_region())

    response = sqs.receive_message(
        QueueUrl=_get_queue_url(),
        MaxNumberOfMessages=max(1, min(max_messages, 10)),
        WaitTimeSeconds=max(0, min(wait_time_seconds, 20)),
    )

    messages = response.get("Messages", [])
    processed = 0
    skipped = 0

    for message in messages:
        receipt_handle = message["ReceiptHandle"]

        try:
            event = _extract_login_event(message.get("Body", ""))
            if event is None:
                # Drop malformed/non-login messages so they do not repeatedly trigger noise.
                sqs.delete_message(
                    QueueUrl=_get_queue_url(),
                    ReceiptHandle=receipt_handle,
                )
                skipped += 1
                continue

            sns_message = (
                "Bank chatbot login alert\n"
                f"User: {event['user_name']}\n"
                f"Account type: {event['account_type']}\n"
                f"Time (UTC): {event['logged_in_at']}"
            )

            sms_message = (
                "Login alert: "
                f"{event['user_name']} ({event['account_type']}) at {event['logged_in_at']}"
            )

            sns.publish(
                TopicArn=_get_topic_arn(),
                Subject="Bank Chatbot Login Alert",
                Message=json.dumps({
                    "default": sns_message,
                    "email": sns_message,
                    "sms": sms_message,
                }),
                MessageStructure="json",
            )

            sqs.delete_message(
                QueueUrl=_get_queue_url(),
                ReceiptHandle=receipt_handle,
            )
            processed += 1
        except Exception:
            # Keep message in queue for retry if processing failed.
            continue

    return {
        "processed": processed,
        "skipped": skipped,
    }
