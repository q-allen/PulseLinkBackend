"""
doctors/face_verification.py

Face verification using AWS Rekognition (replaces local face_recognition/dlib).
Verifies that all three face photos contain the same person,
and optionally verifies they match the face on the PRC card image.
"""

from typing import Tuple, Optional
from .aws_liveness import compare_face_to_prc, _get_rekognition_client
from botocore.exceptions import ClientError


def _read_image_bytes(image_field) -> bytes:
    if hasattr(image_field, 'read'):
        image_field.seek(0)
        return image_field.read()
    with open(image_field.path, 'rb') as f:
        return f.read()


def _compare_two_faces(source_bytes: bytes, target_bytes: bytes, threshold: float = 80.0) -> bool:
    client = _get_rekognition_client()
    try:
        response = client.compare_faces(
            SourceImage={"Bytes": source_bytes},
            TargetImage={"Bytes": target_bytes},
            SimilarityThreshold=threshold,
        )
        matches = response.get("FaceMatches") or []
        return len(matches) > 0 and matches[0].get("Similarity", 0) >= threshold
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "InvalidParameterException":
            return False  # No face detected
        raise


def verify_face_photos(face_front, face_left, face_right, prc_card_image: Optional[object] = None) -> Tuple[bool, str]:
    """
    Verify that all three face photos contain faces and match the same person
    using AWS Rekognition CompareFaces.
    """
    try:
        front_bytes = _read_image_bytes(face_front)
        left_bytes = _read_image_bytes(face_left)
        right_bytes = _read_image_bytes(face_right)

        if not _compare_two_faces(front_bytes, left_bytes):
            return False, "Face photos do not match - please ensure all photos are of the same person"

        if not _compare_two_faces(front_bytes, right_bytes):
            return False, "Face photos do not match - please ensure all photos are of the same person"

        if not _compare_two_faces(left_bytes, right_bytes):
            return False, "Face photos do not match - please ensure all photos are of the same person"

        if prc_card_image is not None:
            match, message = compare_face_to_prc(front_bytes, prc_card_image)
            if not match:
                return False, message

        return True, "Face verification successful"

    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Face verification error: {str(e)}"
