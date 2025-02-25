import json

def encode_message(message_dict):
    """
    Encode a dictionary into a JSON string and then to bytes.
    """
    try:
        return json.dumps(message_dict).encode('utf-8')
    except Exception as e:
        print("Error encoding message:", e)
        return None

def decode_message(message_bytes):
    """
    Decode bytes into a JSON object (dictionary).
    """
    try:
        return json.loads(message_bytes.decode('utf-8'))
    except Exception as e:
        print("Error decoding message:", e)
        return None
