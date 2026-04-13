# Automated Face Verification

## Overview
Face verification is now **automatic** when doctors upload their three face photos (front, left, right) during onboarding.

## How It Works

1. **Doctor uploads three photos**: front-facing, left-side, and right-side
2. **Automatic verification runs** when all three photos are present:
   - Detects faces in each photo
   - Verifies exactly one face per photo
   - Compares all three faces to ensure they match the same person
   - Sets `is_face_verified=True` automatically if verification passes

3. **Error handling**: If verification fails, the API returns a clear error message:
   - "No face detected in [photo]"
   - "Multiple faces detected in [photo]"
   - "Face photos do not match - please ensure all photos are of the same person"

## Technical Details

- **Library**: `face_recognition` (built on dlib)
- **Tolerance**: 0.6 (standard face matching threshold)
- **Location**: `doctors/face_verification.py`
- **Integration**: `DoctorProfileCompletionSerializer.update()`

## API Behavior

### Before (Manual)
```json
PATCH /api/doctors/me/complete/
{
  "face_front": <file>,
  "face_left": <file>,
  "face_right": <file>,
  "is_face_verified": true  // ❌ Manual flag
}
```

### After (Automatic)
```json
PATCH /api/doctors/me/complete/
{
  "face_front": <file>,
  "face_left": <file>,
  "face_right": <file>
  // ✅ is_face_verified set automatically
}
```

## Installation

```bash
pip install -r requirements.txt
```

Note: `face_recognition` requires `cmake` and `dlib`. On Windows, you may need to install Visual Studio Build Tools.

## Benefits

- ✅ No manual verification needed
- ✅ Prevents mismatched photos
- ✅ Ensures photo quality (face must be detectable)
- ✅ Prevents multiple people in photos
- ✅ Immediate feedback to doctors
