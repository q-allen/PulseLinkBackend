"""
doctors/face_verification.py

Automated face verification using face detection and comparison.
Verifies that all three face photos (front, left, right) contain the same person.
"""

import io
from typing import Tuple
from PIL import Image
import face_recognition
import numpy as np


def verify_face_photos(face_front, face_left, face_right) -> Tuple[bool, str]:
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
        
        # Detect faces in each image
        front_encodings = face_recognition.face_encodings(front_img)
        left_encodings = face_recognition.face_encodings(left_img)
        right_encodings = face_recognition.face_encodings(right_img)
        
        # Verify each image contains exactly one face
        if len(front_encodings) == 0:
            return False, "No face detected in front photo"
        if len(left_encodings) == 0:
            return False, "No face detected in left photo"
        if len(right_encodings) == 0:
            return False, "No face detected in right photo"
        
        if len(front_encodings) > 1:
            return False, "Multiple faces detected in front photo"
        if len(left_encodings) > 1:
            return False, "Multiple faces detected in left photo"
        if len(right_encodings) > 1:
            return False, "Multiple faces detected in right photo"
        
        # Get the single face encoding from each image
        front_encoding = front_encodings[0]
        left_encoding = left_encodings[0]
        right_encoding = right_encodings[0]
        
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
        
        return True, "Face verification successful"
        
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
