# Created: 2025-07-15 18:37:24
# Last Modified: 2025-07-30 15:07:06
# Author: Scott Cadreau

# Email service exports
from .email_service import (
    send_email,
    create_attachment_from_file,
    create_attachment_from_data,
    verify_ses_configuration,
    test_secrets_configuration,
    EmailAttachment
)

__all__ = [
    'send_email',
    'create_attachment_from_file',
    'create_attachment_from_data',
    'verify_ses_configuration',
    'test_secrets_configuration',
    'EmailAttachment'
]
