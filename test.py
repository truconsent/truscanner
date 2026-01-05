import boto3
from botocore.exceptions import ClientError
AWS_REGION = "us-east-1"  # change if your SES is in another region
SENDER = "Updates <no-reply@updates.truconsent.io>"
RECIPIENT = "deepakraja.ra@cobuildx.ai"  # replace with your email
SUBJECT = "Amazon SES Test Email"
BODY_TEXT = """Hello,
This is a test email sent using Amazon SES from updates.truconsent.io.
If you received this, SES is configured correctly.
Regards,
TruConsent
"""
BODY_HTML = """\
<html>
<head></head>
<body>
  <h2>Amazon SES Test</h2>
  <p>This is a test email sent using <b>Amazon SES</b>.</p>
  <p><b>Domain:</b> updates.truconsent.io</p>
  <p>If you received this, SES is configured correctly.</p>
</body>
</html>
"""
def send_test_email():
    client = boto3.client("ses", region_name=AWS_REGION)
    try:
        response = client.send_email(
            Source=SENDER,
            Destination={
                "ToAddresses": [RECIPIENT],
            },
            Message={
                "Subject": {
                    "Data": SUBJECT,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": BODY_TEXT,
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": BODY_HTML,
                        "Charset": "UTF-8",
                    },
                },
            },
        )
        print("Email sent successfully!")
        print("Message ID:", response["MessageId"])
    except ClientError as e:
        print("Error sending email:")
        print(e.response["Error"]["Message"])
if __name__ == "__main__":
    send_test_email()