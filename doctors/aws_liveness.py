from __future__ import annotations

from datetime import timezone as dt_timezone
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


class LivenessConfigError(RuntimeError):
    """Raised when AWS liveness configuration is incomplete."""


def _build_permission_error(action: str, *, role_arn: str = "") -> str:
    if action == "CreateFaceLivenessSession":
        return (
            "AWS denied rekognition:CreateFaceLivenessSession. The backend IAM "
            "user or role tied to AWS_ACCESS_KEY_ID must allow "
            "rekognition:CreateFaceLivenessSession."
        )
    if action == "GetFaceLivenessSessionResults":
        return (
            "AWS denied rekognition:GetFaceLivenessSessionResults. The backend IAM "
            "user or role tied to AWS_ACCESS_KEY_ID must allow "
            "rekognition:GetFaceLivenessSessionResults."
        )
    if action == "AssumeRole":
        target = role_arn or "the configured frontend role"
        return (
            f"AWS denied sts:AssumeRole for {target}. The backend IAM user or role "
            "tied to AWS_ACCESS_KEY_ID must allow sts:AssumeRole on that role, "
            "and the target role trust policy must allow that principal."
        )
    return f"AWS denied {action}."


def _raise_liveness_aws_error(
    exc: Exception,
    *,
    action: str,
    role_arn: str = "",
) -> None:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error") or {}
        code = str(error.get("Code") or "ClientError")
        message = str(error.get("Message") or str(exc))

        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            raise LivenessConfigError(
                f"{_build_permission_error(action, role_arn=role_arn)} AWS said: {message}"
            ) from exc

        if code in {"UnrecognizedClientException", "InvalidSignatureException"}:
            raise LivenessConfigError(
                "AWS credentials were rejected. Check AWS_ACCESS_KEY_ID, "
                "AWS_SECRET_ACCESS_KEY, and AWS_REGION in CareConnect_backend/.env."
            ) from exc

        raise LivenessConfigError(f"AWS {action} failed ({code}): {message}") from exc

    raise LivenessConfigError(f"AWS {action} failed: {exc}") from exc


def _get_region() -> str:
    region = getattr(settings, "AWS_REGION", "")
    if not region:
        raise LivenessConfigError("AWS_REGION is not configured.")
    return region


def _get_rekognition_client():
    return _get_boto3_session().client("rekognition")


def _get_sts_client():
    return _get_boto3_session().client("sts")


def _get_boto3_session():
    access_key = getattr(settings, "AWS_ACCESS_KEY_ID", "") or ""
    secret_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", "") or ""

    if not access_key or not secret_key:
        raise LivenessConfigError(
            "Backend AWS credentials are missing. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in CareConnect_backend/.env, or run the backend "
            "with an IAM role/profile that can call Rekognition and STS."
        )

    return boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=_get_region(),
    )


def create_liveness_session() -> str:
    """Create a single-use Rekognition Face Liveness session."""
    try:
        response = _get_rekognition_client().create_face_liveness_session()
        return response["SessionId"]
    except (ClientError, BotoCoreError) as exc:
        _raise_liveness_aws_error(exc, action="CreateFaceLivenessSession")


def get_liveness_results(session_id: str) -> dict[str, Any]:
    """Fetch the final liveness session results from Rekognition."""
    try:
        results = _get_rekognition_client().get_face_liveness_session_results(
            SessionId=session_id,
        )
        return results
    except (ClientError, BotoCoreError) as exc:
        _raise_liveness_aws_error(exc, action="GetFaceLivenessSessionResults")


def get_temporary_liveness_credentials() -> dict[str, str]:
    """
    Assume the frontend role (LivenessFrontendRole) 
    Returns temporary credentials for the browser (FaceLivenessDetector).
    """
    role_arn = getattr(settings, "AWS_LIVENESS_ROLE_ARN", "")
    if not role_arn:
        raise LivenessConfigError("AWS_LIVENESS_ROLE_ARN is not configured.")

    external_id = getattr(settings, "AWS_LIVENESS_EXTERNAL_ID", "pulselink-liveness-2026")

    try:
        response = _get_sts_client().assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"pulselink-liveness-{uuid4().hex[:12]}",
            DurationSeconds=900,
            ExternalId=external_id,
        )
        credentials = response["Credentials"]
    except (ClientError, BotoCoreError) as exc:
        _raise_liveness_aws_error(exc, action="AssumeRole", role_arn=role_arn)
        return {}  # unreachable; _raise_liveness_aws_error always raises

    expiration = credentials["Expiration"]
    if getattr(expiration, "tzinfo", None) is not None:
        expiration = expiration.astimezone(dt_timezone.utc).replace(tzinfo=None)

    return {
        "accessKeyId": credentials["AccessKeyId"],
        "secretAccessKey": credentials["SecretAccessKey"],
        "sessionToken": credentials["SessionToken"],
        "expiration": expiration.isoformat() + "Z",
    }


def extract_reference_image_bytes(results: dict[str, Any]) -> bytes | None:
    reference = results.get("ReferenceImage") or {}
    return reference.get("Bytes")


def extract_audit_image_bytes(results: dict[str, Any]) -> list[bytes]:
    audit_images = results.get("AuditImages") or []
    return [item["Bytes"] for item in audit_images if item.get("Bytes")]


def compare_face_to_prc(reference_bytes: bytes, prc_image_field) -> tuple[bool, str]:
    """
    Use Rekognition CompareFaces to check if the liveness reference image
    matches the face on the PRC card.

    Returns (match: bool, message: str).
    """
    try:
        if hasattr(prc_image_field, "read"):
            prc_image_field.seek(0)
            prc_bytes = prc_image_field.read()
        else:
            with open(prc_image_field.path, "rb") as f:
                prc_bytes = f.read()
    except Exception as exc:
        return False, f"Could not read PRC card image: {exc}"

    try:
        response = _get_rekognition_client().compare_faces(
            SourceImage={"Bytes": reference_bytes},
            TargetImage={"Bytes": prc_bytes},
            SimilarityThreshold=80.0,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDenied", "AccessDeniedException"}:
            raise LivenessConfigError(
                "AWS denied rekognition:CompareFaces. Add \"rekognition:CompareFaces\" "
                "to the backend IAM user policy for pulselink-rekognition."
            ) from exc
        return False, f"Face comparison failed: {exc}"
    except BotoCoreError as exc:
        return False, f"Face comparison failed: {exc}"

    matches = response.get("FaceMatches") or []
    if not matches:
        return False, "Your face does not match the photo on your PRC card. Please ensure your PRC card shows a clear front-facing photo."

    similarity = matches[0].get("Similarity", 0)
    if similarity < 80.0:
        return False, "Your face does not match the photo on your PRC card. Please ensure your PRC card shows a clear front-facing photo."

    return True, "Face matches PRC card."


def parse_liveness_status(results: dict[str, Any]) -> str:
    return str(results.get("Status") or "").upper()


def parse_liveness_confidence(results: dict[str, Any]) -> float:
    try:
        return float(results.get("Confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def is_retryable_liveness_error(exc: Exception) -> bool:
    if isinstance(exc, LivenessConfigError):
        return False
    if isinstance(exc, (ClientError, BotoCoreError)):
        return True
    return False