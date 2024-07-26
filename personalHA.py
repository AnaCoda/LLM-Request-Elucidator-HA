import json
from openai import OpenAI
import requests

# Sends a Jinja2 template to Home Assistant, can be used to retrieve information about entities and states
def send_template_request(template):
    url = "https://<your_instance>:8000/api/template"
    headers = {
        "Authorization": "Bearer <your_token>",
        "Content-Type": "application/json"
    }
    payload = {"template": template}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        err = f"Error sending template request: {e}"
        return err

# Get initial data
entity_list = send_template_request("{{ states | map(attribute='entity_id') | list | join(', ') }}")
if entity_list:
    print("Response saved to entity_list successfully.")
else:
    print("Failed to get entity list.")

area_list = send_template_request("{{ areas() }}")
if area_list:
    print("Response saved to area_list successfully.")
else:
    print("Failed to get area list.")

labels_list = send_template_request("{{ labels() }}")
if labels_list:
    print("Response saved to labels_list successfully.")
else:
    print("Failed to get area list.")

# Sends an intent request to home assistant, can be used to change the state of a device
def send_ACTION_request(ACTION_data):
    url = "https://<your_instance>:8000/api/intent/handle"
    headers = {
        "Authorization": "Bearer <your_token>",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=ACTION_data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending intent request: {e}")
        return None

# Define the prompt templates for Query, Followup, Answer and Action
# Description is what the model uses to decide on the action to take
# prompt_template is what the model is prompted after it's decided on an action (more detailed)
query_prompt_info = {
    "name": "QUERY",
    "description": "For querying Home Assistant for state of available devices. For example, if you need to list devices IDs, or get the temperature of a sensor. Use FOLLOWUP instead if not sure which device.",
    "prompt_template": """You are an AI capable of using Jinja2 templates for querying Home Assistant.
    Here are some example templates:
    {{ area_entities('kitchen') }} <- Use this if you are looking for a specific device name in a room
    # Is the current time past 10:15?
    {{ now() > today_at("10:15") }}
    {{ states.device_tracker.paulus.state }}
    {{ states.light | map(attribute='entity_id') | list }} <- use this to list all the lights
    {{ label_entities('temperature') }}
    You may list all sensors. Do not filter too much. Try again if failed.
    Here is the task:\n{input}\n.
    You are not allowed to output anything except the template. Do not include any explanations."""
}

followup_prompt_info = {
    "name": "FOLLOWUP",
    "description": "Use this to ask English follow-up questions when anything is ambiguous, such as 'Turn off the bedroom light', 'Turn off my computers', or to choose between more than one entity.",
    "prompt_template": "Ask a follow-up question to understand the user's home automation request better. Be brief, keep it between 2 to 10 words. Here is the user request: {input}"
}

answer_prompt_info = {
    "name": "ANSWER",
    "description": "Use this to give an answer to the user if they asked a question about something, and you already have the answer.",
    "prompt_template": "Here is the user request: {input}. Respond with the information you have."
}

action_prompt_info = {
    "name": "ACTION",
    "description": "This prompt is only for turning something on and off with Home Assistant API calls when the request is clear and specific with device ID and/or room. You must know the exact device name to use this.",
    "prompt_template": """You are an AI that creates ACTIONs for Home Assistant API calls.
    Here are some example API ACTIONs:
        HassTurnOn

    Turns on a device or entity

        name/area/device_class - Device class of devices/entities in an area
    Send only { "name": "HassTurnOn", "data": { "area": "kitchen" } } for a room
    { "name": "HassTurnOn", "data": { "name": "light1blah" } } for a singular entity
    { "name": "HassTurnOn", "data": { "name": "light2blah" } }*{ "name": "HassTurnOn", "data": { "name": "light2blah" } } for multiple lights

    HassTurnOff

    Turns off a device or entity

    Here is the task:\n{input}\n.
    You are not allowed to output anything except the ACTION. Do not include any explanations.
    Each ACTION can only target one entity/room/area. If you want to do multiple (no more than three), separate each ACTION with a asterisk *.
    Ignore scenes."""
}

# Instantiate the LLM
client = OpenAI(api_key='dummy', base_url='http://127.0.0.1:1234/v1/')

# Create System message which includes the short description of actions, and some of the available areas and labels.
SYSTEM_MESSAGE = f"""
You are 'Al', a precise AI assistant that controls the devices in a house. Complete the following task as instructed.
You have access to the following actions:
{query_prompt_info["name"]}: {query_prompt_info["description"]}
{followup_prompt_info["name"]}: {followup_prompt_info["description"]}
{answer_prompt_info["name"]}: {answer_prompt_info["description"]}
{action_prompt_info["name"]}: {action_prompt_info["description"]}
Here are the available areas: {area_list}
Here are the available labels: {labels_list}
Always ask FOLLOWUP, use common sense. Don't choose an entity by default.
Use QUERY for information and ACTION for actions.
To take one of the actions, output only the name of the action. One word.
"""

# Gets a response from the AI
def get_response(chat_history):
    response = client.chat.completions.create(
        model="local-model",
        messages=chat_history,
        temperature=0.5,
        stop=None,
        max_tokens=50,
    )
    chat_history.append({"role": "assistant", "content": response.choices[0].message.content.strip()})
    return response.choices[0].message.content.strip()

def main():
    system_message = SYSTEM_MESSAGE
    chat_history = [{"role": "system", "content": system_message}]
    action_type = ''

    # Conversation loop
    while True:
        chat_history.append({"role": "user", "content": "FOLLOW THE SYSTEM MESSAGE OUTPUT ONLY ONE WORD, QUERY FOLLOWUP ANSWER OR ACTION"})

        # If it was a QUERY then we've already gotten the query response from Home Assistant (later in this loop), don't prompt the user.
        if action_type == 'QUERY':
            user_input = result
        else:
            user_input = input("User: ")
            if user_input.lower() in ['exit', 'bye', 'end']:
                print("Exiting the conversation.")
                break

        chat_history.append({"role": "user", "content": user_input})
        
        # Get the action the LLM decides on

        model_response = get_response(chat_history)
        print("Model Response: ", model_response)
        
        if 'FOLLOWUP' in model_response:
            instruction = {"role": "user", "content": followup_prompt_info["prompt_template"].replace('{input}', user_input)}
            action_type = 'FOLLOWUP'
        elif 'ANSWER' in model_response:
            instruction = {"role": "user", "content": answer_prompt_info["prompt_template"].replace('{input}', user_input)}
            action_type = 'ANSWER'
        elif 'ACTION' in model_response:
            instruction = {"role": "user", "content": action_prompt_info["prompt_template"].replace('{input}', user_input)}
            action_type = 'ACTION'
        else:
            instruction = {"role": "user", "content": query_prompt_info["prompt_template"].replace('{input}', user_input)}
            action_type = 'QUERY'

        chat_history.append(instruction)

        model_response = get_response(chat_history)
        print("\nModel Action: ", model_response)
        if action_type == 'ACTION':                    # If we're performing an action/intent, then send it to Home Assistant
            for ACTION in model_response.split('*'):
                resp = ACTION.replace('*','')
                print('resp', resp)
                try:
                    ACTION_data = json.loads(resp)
                    if isinstance(ACTION_data, list):
                        for i in ACTION_data:
                            result = send_ACTION_request(i)
                            print(i)
                            print(f"ACTION request sent successfully: {result}")
                    else:
                        result = send_ACTION_request(ACTION_data)
                        print(f"ACTION request sent successfully: {result}")
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON format for ACTION data: {e}")
                except requests.exceptions.RequestException as e:
                    print(f"Error sending ACTION request: {e}")
        elif action_type == 'QUERY':                    # If we're making a query, then send it to Home Assistant
            result = send_template_request(model_response)
            if result:
                print(f"Query result: {result}")
            else:
                print("Failed to execute query: {e}")
        # Otherwise it's either an answer or or followup question so we can just ask/tell the user and wait for their response


if __name__ == "__main__":
    main()
