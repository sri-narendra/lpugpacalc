"""Student profile information."""
import json


def parse_profile(raw_data):
    """Parse GetStudentBasicInformation response (JSON list or dict)."""
    if not raw_data:
        return {}
    if isinstance(raw_data, list):
        return raw_data[0] if raw_data else {}
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
            if isinstance(data, list):
                return data[0] if data else {}
            return data
        except (json.JSONDecodeError, TypeError):
            pass
    return raw_data


def extract_profile_fields(profile: dict) -> dict:
    """Extract readable fields from profile dict."""
    if not profile:
        return {}
    return {
        'reg_no': profile.get('Registrationnumber') or profile.get('RegistrationNo') or '',
        'program': profile.get('Program', ''),
        'section': profile.get('Section', ''),
        'batch': profile.get('BatchYear') or profile.get('Batch') or '',
        'admission_session': profile.get('AdmissionSession', ''),
        'student_name': profile.get('StudentName') or profile.get('Name') or '',
        'email': profile.get('Email') or profile.get('EmailId') or '',
        'phone': profile.get('PhoneNo') or profile.get('Mobile') or '',
        'profile_image': profile.get('StudentPicture', ''),
    }
