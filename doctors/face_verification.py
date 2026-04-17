"""
doctors/face_verification.py

Automated face verification using face detection and comparison.
Verifies that all three face photos (front, left, right) contain the same person,
and optionally verifies they match the face on the PRC card image.
"""

import io
from typing import Tuple, Optional
from PIL import Image
import face_recognition
import numpy as np


def verify_face_photos(face_front, face_left, face_right, prc_card_image: Optional[object] = None) -> Tuple[bool, str]:
    """
    Automatically verify that all three face photos contain faces and match the same person.
    
    Args:
        face_front: ImageField or file object for front-facing photo
        face_left: ImageField or file object for left-side photo
        face_right: ImageField or file object for right-side photo
    
    Returns:
        Tuple of (is_verified: bool, message: str)
    """
    try:
        # Load images
        front_img = _load_image(face_front)
        left_img = _load_image(face_left)
        right_img = _load_image(face_right)

        # Get a single face encoding per photo
        front_encoding = _single_face_encoding(front_img, "front photo")
        left_encoding = _single_face_encoding(left_img, "left photo")
        right_encoding = _single_face_encoding(right_img, "right photo")
        
        # Compare faces - tolerance of 0.6 is standard (lower = stricter)
        tolerance = 0.6
        
        # Compare front with left
        front_left_match = face_recognition.compare_faces(
            [front_encoding], left_encoding, tolerance=tolerance
        )[0]
        
        # Compare front with right
        front_right_match = face_recognition.compare_faces(
            [front_encoding], right_encoding, tolerance=tolerance
        )[0]
        
        # Compare left with right
        left_right_match = face_recognition.compare_faces(
            [left_encoding], right_encoding, tolerance=tolerance
        )[0]
        
        # All three photos must match
        if not (front_left_match and front_right_match and left_right_match):
            return False, "Face photos do not match - please ensure all photos are of the same person"

        # Optional: verify PRC card face matches the live photos
        if prc_card_image is not None:
            prc_img = _load_image(prc_card_image)
            prc_encoding = _single_face_encoding(prc_img, "PRC card photo")

            # Use the average encoding of the three live photos for stability
            live_avg = np.mean([front_encoding, left_encoding, right_encoding], axis=0)
            prc_match = face_recognition.compare_faces(
                [live_avg], prc_encoding, tolerance=tolerance
            )[0]
            if not prc_match:
                return False, "PRC card face does not match the live face photos"
        
        return True, "Face verification successful"
        
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Face verification error: {str(e)}"


def _load_image(image_field):
    """Load image from Django ImageField or file object into numpy array."""
    try:
        # Try to read from ImageField
        if hasattr(image_field, 'read'):
            image_field.seek(0)
            img_data = image_field.read()
        else:
            # It's already a file path or URL
            with open(image_field.path, 'rb') as f:
                img_data = f.read()
        
        # Convert to PIL Image then to numpy array
        img = Image.open(io.BytesIO(img_data))
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return np.array(img)
    except Exception as e:
        raise ValueError(f"Failed to load image: {str(e)}")


def _single_face_encoding(image, label: str):
    """Return the single face encoding or raise a ValueError with a clear message."""
    encodings = face_recognition.face_encodings(image)
    if len(encodings) == 0:
        raise ValueError(f"No face detected in {label}")
    if len(encodings) > 1:
        raise ValueError(f"Multiple faces detected in {label}")
    return encodings[0]
