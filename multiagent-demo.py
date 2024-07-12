import os
import autogen
from typing import Dict, List
from autogen import Agent

# Get contents of files
def get_file_content(file_path: str) -> str:
    with open(file_path, "r") as file:
        return file.read()  # Read the file and return the content as a string 

# Read testdata files
plsqlScript = get_file_content("testdata-sql-plsql.sql")
tablesScript = get_file_content("testdata-sql-tables.sql")
departmentsData = get_file_content("testdata-csv-departments.csv")
employeesData = get_file_content("testdata-csv-employees.csv") 
salariesData = get_file_content("testdata-csv-salaries.csv")

# Anthropic's Sonnet llm config
ANTHROPIC_CONFIG = [
    {
        "api_type": "anthropic",
        "model": "claude-3-5-sonnet-20240620",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "cache_seed": None,
    },
]

LLM_CONFIG = {"config_list": ANTHROPIC_CONFIG, "cache_seed": None}

# Configuration constants
PLANNER_SYSTEM_MESSAGE = """
- Suggest a plan involving an engineer who writes code, a reviewer who checks code, and an executor who runs code.
- Explain the plan clearly, specifying which step is performed by each participant.
- Do not write code; ask the engineer to do this by saying "Dear engineer" before the instructions.
- Do not review code; engineer will pass this task to the reviewer.
- Do not run code; engineer will do this when testing code.
- After the plan has executed successfully, ask the user to check the result by saying "Dear user"
"""

ENGINEER_SYSTEM_MESSAGE = """
- Follow an approved plan.
- Write Python/Shell code to solve tasks.
- Wrap the code in a code block that specifies the script type.
- Write safe and secure code. This includes validating user inputs, avoiding infinite loops, and ensuring no sensitive data is exposed.
- Include error handling if necessary. Code should be robust and able to handle edge cases.
- Ensure the user can't modify your code; do not suggest incomplete code that requires others to modify.
- Do not use a code block if it's not intended to be executed by the executor.
- Do not include multiple code blocks in one response.
- Do not ask others to copy and paste the result.
- Check the execution result returned by the executor.
- When ready to test the code, ask the reviewer to check it by saying "Dear reviewer."
- Implement any suggestions made by the reviewer. If the reviewer asks for changes, output the full code again.
- After the reviewer approves the code, test it by running it. Do this by saying "Dear executor."
- If the result indicates an error, fix the error and output the full code again.
- Suggest the full code instead of partial code or code changes.
- If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumptions, collect additional info, and think of a different approach.
- Document the code if necessary using Google Docstrings formatting.
- For any 'def' functions, add unit tests at the end of the code encapsulated by comments. Also cover error cases in the unit tests.
- Any mock data should be separate from the business logic. It should be easy to change to production data. Keep the mock data outside 'def' functions.
"""

REVIEWER_SYSTEM_MESSAGE = """
- You are a reviewer.
- Follow an approved plan.
- Review the code written by the engineer.
- Do not write code.
- Follow strict style rules for code review.
- Make sure any 'def' functions have unit tests at the end of the code encapsulated by comments.
- Always finish feedback with "code: APPROVED" or "code: REJECTED" depending on your feedback.
- If the code is incorrect, provide feedback to the engineer and address the engineer with "Dear engineer."
- Reject code until you have no further improvement comments.
- The engineer will fix the code and output the code again.
"""

EXECUTOR_SYSTEM_MESSAGE = """
- Follow an approved plan.
- Run the code written by the engineer.
- Do not write or review code.
- Execute the code and return the result to the engineer.
- If the code execution fails, provide the error message to the engineer by saying "Dear engineer."
- Run both the code and the unit tests; all should return the expected results.
- If the code execution is successful, return the result to the planner by saying "Dear planner."
"""

def create_user_proxy_agent(name: str, system_message: str, code_execution_config: bool):
    """Create a UserProxyAgent with the given parameters."""
    return autogen.UserProxyAgent(
        name=name,
        system_message=system_message,
        code_execution_config=code_execution_config,
    )

def create_assistant_agent(name: str, system_message: str):
    """Create an AssistantAgent with the given parameters."""
    return autogen.AssistantAgent(
        name=name,
        system_message=system_message,
        llm_config=LLM_CONFIG,
    )

# Create agents
user_proxy = create_user_proxy_agent(
    name="Admin",
    system_message="A human admin.",
    code_execution_config=False,
)

planner = create_assistant_agent(
    name="Planner",
    system_message=PLANNER_SYSTEM_MESSAGE,
)

engineer = create_assistant_agent(
    name="Engineer",
    system_message=ENGINEER_SYSTEM_MESSAGE,
)

reviewer = create_assistant_agent(
    name="Reviewer",
    system_message=REVIEWER_SYSTEM_MESSAGE,
)

executor = autogen.UserProxyAgent(
    name="Executor",
    system_message=EXECUTOR_SYSTEM_MESSAGE,
    human_input_mode="NEVER",
    code_execution_config={
        "last_n_messages": 3,
        "work_dir": "code",
        "use_docker": False,
    },  # Please set use_docker=True if docker is available to run the generated code. Using docker is safer than running the generated code directly.
)


def custom_speaker_selection_func(last_speaker: Agent, groupchat: autogen.GroupChat):
    """
    Selects the next speaker in a multi-agent conversation based on the previous messages.

    Parameters:
        last_speaker (Agent): The agent who spoke last.
        groupchat (autogen.GroupChat): The group chat containing the conversation messages.

    Returns:
        Agent: The agent selected to speak next.

    Description:
        This function determines the next agent to speak in a multi-agent conversation based on the previous messages in the group chat.
    """
    messages = groupchat.messages

    if len(messages) <= 1:
        return planner
    
    elif "Dear user" in messages[-1]["content"]:
        return user_proxy
    
    elif "Dear planner" in messages[-1]["content"]:
        return planner
    
    elif "Dear engineer" in messages[-1]["content"]:
        return engineer

    elif "Dear reviewer" in messages[-1]["content"]:
        return reviewer
    
    elif "Dear executor" in messages[-1]["content"]:
        return executor

    elif last_speaker is executor:
        if "exitcode: 1" in messages[-1]["content"]:
            # If the last message indicates an error, let the engineer improve the code
            return engineer
        else:
            # Otherwise, let the planner speak
            return planner

    else:
        return planner
    
groupchat = autogen.GroupChat(
agents=[user_proxy, engineer, reviewer, planner, executor],
messages=[],
max_round=20,
speaker_selection_method=custom_speaker_selection_func,
)

manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=LLM_CONFIG)

user_proxy.initiate_chat(
    manager, message=f"""
Please rewerite this Oracle PL/SQL function into a python code function. Code should be written as a single program.
The function should return the results as a logical structure. Then print it similar to the PL/SQL output.

PL/SQL function:
 ```
{plsqlScript}
```

For context, here's the tables used in the PL/SQL function:
```
{tablesScript}
```

This is for testing purpose, so you don't need to make code for connecting to Oracle database. Instead use the data from the following csv data when testing logic. The csv data contains the following data:
departments.csv:
```
{departmentsData}
```
employees.csv:
```
{employeesData}
```
salaries.csv:
```
{salariesData}
```

When you are satisfied with the code present the result to user. For the test use hardcoded CSV data provided above but keep it separate from the business logic. No need for logic reading for CSV-files.
Logic should be written so it can easiliy be changed to read from the production Oracle database.

The expected output for Department 1 should be:
```
Emp ID: 201, Name: John Doe, Salary: 50000, Bonus: 5000
Emp ID: 202, Name: Jane Smith, Salary: 55000, Bonus: 5500
Total Salary for Department 1: 115500
    """
)