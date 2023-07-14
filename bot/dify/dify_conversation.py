conversation_id = ""

def update_conversation_id(session_id):
    global conversation_id
    conversation_id = session_id

def get_conversation_id():
    global conversation_id
    return conversation_id