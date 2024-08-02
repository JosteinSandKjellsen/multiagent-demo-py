import os
import logging
from typing import Dict, List
from dataclasses import dataclass

import autogen
from autogen import Agent, GroupChat, GroupChatManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AgentConfig:
    name: str
    system_message: str
    is_user_proxy: bool
    human_input_mode: str
    code_execution_config: Dict = None

# Constants
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-3-5-sonnet-20240620"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "mixtral-8x7b-32768"
MAX_CHAT_ROUNDS = 20
USE_DOCKER = os.getenv("AUTOGEN_USE_DOCKER", "False").lower() in ("true", "1", "t")
API_TYPE = os.getenv("API_TYPE", "anthropic").lower()  # Default to Anthropic if not set

# Agent system messages
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

def get_file_content(file_path: str) -> str:
    """Read and return the content of a file."""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except IOError as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise

def create_llm_config() -> Dict:
    """Create and return the LLM configuration based on the selected API."""
    if API_TYPE == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        return {
            "config_list": [
                {
                    "api_type": "anthropic",
                    "model": ANTHROPIC_MODEL,
                    "api_key": ANTHROPIC_API_KEY,
                }
            ],
            "cache_seed": None,
        }
    elif API_TYPE == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        return {
            "config_list": [
                {
                    "api_type": "groq",
                    "model": GROQ_MODEL,
                    "api_key": GROQ_API_KEY,
                }
            ],
            "cache_seed": None,
        }
    else:
        raise ValueError(f"Invalid API_TYPE: {API_TYPE}. Must be 'anthropic' or 'groq'.")

def create_agent(config: AgentConfig, llm_config: Dict) -> Agent:
    """Create and return an agent based on the provided configuration."""
    if config.is_user_proxy:
        return autogen.UserProxyAgent(
            name=config.name,
            system_message=config.system_message,
            human_input_mode=config.human_input_mode,
            code_execution_config=config.code_execution_config,
        )
    else:
        return autogen.AssistantAgent(
            name=config.name,
            system_message=config.system_message,
            llm_config=llm_config,
        )

def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat) -> Agent:
    """Select the next speaker based on the conversation flow."""
    messages = groupchat.messages

    if len(messages) <= 1:
        return groupchat.agents[1]  # Planner
    
    last_message = messages[-1]["content"]
    
    speaker_map = {
        "Dear user": groupchat.agents[0],  # User Proxy
        "Dear planner": groupchat.agents[1],  # Planner
        "Dear engineer": groupchat.agents[2],  # Engineer
        "Dear reviewer": groupchat.agents[3],  # Reviewer
        "Dear executor": groupchat.agents[4],  # Executor
    }

    for key, agent in speaker_map.items():
        if key in last_message:
            return agent

    if last_speaker == groupchat.agents[4]:  # Executor
        return groupchat.agents[2] if "exitcode: 1" in last_message else groupchat.agents[1]

    return groupchat.agents[1]  # Default to Planner

def main():
    # Read test data
    plsql_script = get_file_content("testdata-sql-plsql.sql")
    tables_script = get_file_content("testdata-sql-tables.sql")
    departments_data = get_file_content("testdata-csv-departments.csv")
    employees_data = get_file_content("testdata-csv-employees.csv")
    salaries_data = get_file_content("testdata-csv-salaries.csv")

    llm_config = create_llm_config()

    # Create agents
    agents = [
        create_agent(AgentConfig("Admin", "A human admin.", True, "ALWAYS", None), llm_config),
        create_agent(AgentConfig("Planner", PLANNER_SYSTEM_MESSAGE, False, "", None), llm_config),
        create_agent(AgentConfig("Engineer", ENGINEER_SYSTEM_MESSAGE, False, "", None), llm_config),
        create_agent(AgentConfig("Reviewer", REVIEWER_SYSTEM_MESSAGE, False, "", None), llm_config),
        create_agent(AgentConfig("Executor", EXECUTOR_SYSTEM_MESSAGE, True, "NEVER", {
            "last_n_messages": 3,
            "work_dir": "code",
            "use_docker": USE_DOCKER,
        }), llm_config),
    ]

    groupchat = GroupChat(
        agents=agents,
        messages=[],
        max_round=MAX_CHAT_ROUNDS,
        speaker_selection_method=custom_speaker_selection_func,
    )

    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

    task_message = f"""
    Please rewrite this Oracle PL/SQL function into a python code function. Code should be written as a single program.
    The function should return the results as a logical structure. Then print it similar to the PL/SQL output.

    PL/SQL function:
    ```
    {plsql_script}
    ```

    For context, here's the tables used in the PL/SQL function:
    ```
    {tables_script}
    ```

    This is for testing purpose, so you don't need to make code for connecting to Oracle database. Instead use the data from the following csv data when testing logic. The csv data contains the following data:
    departments.csv:
    ```
    {departments_data}
    ```
    employees.csv:
    ```
    {employees_data}
    ```
    salaries.csv:
    ```
    {salaries_data}
    ```

    When you are satisfied with the code present the result to user. For the test use hardcoded CSV data provided above but keep it separate from the business logic. No need for logic reading for CSV-files.
    Logic should be written so it can easily be changed to read from the production Oracle database.

    The expected output for Department 1 should be:
    ```
    Emp ID: 201, Name: John Doe, Salary: 50000, Bonus: 5000
    Emp ID: 202, Name: Jane Smith, Salary: 55000, Bonus: 5500
    Total Salary for Department 1: 115500
    ```
    """

    agents[0].initiate_chat(manager, message=task_message)

if __name__ == "__main__":
    main()