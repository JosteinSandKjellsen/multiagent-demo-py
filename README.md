# Multiagent Demo

This project demonstrates a multi-agent system where different agents (Planner, Engineer, Reviewer, and Executor) collaborate to write, review, and execute code. The agents follow a predefined set of instructions to ensure the code is written, reviewed, and executed correctly.

## Agents

### Planner

- Suggests a plan involving an engineer, a reviewer, and an executor.
- Explains the plan clearly, specifying which step is performed by each participant.
- Does not write, review, or run code.

### Engineer

- Follows an approved plan.
- Writes Python/Shell code to solve tasks.
- Wraps the code in a code block that specifies the script type.
- Asks the reviewer to check the code when ready by saying "Dear reviewer."
- Implements any suggestions made by the reviewer. If the reviewer asks for changes, outputs the full code again.
- After the reviewer approves the code, tests it by running it by saying "Dear executor."
- If the result indicates an error, fixes the error and outputs the full code again.
- Suggests the full code instead of partial code or code changes.
- If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyzes the problem, revisits assumptions, collects additional info, and thinks of a different approach.
- Documents the code if necessary using Google Docstrings formatting.
- For any 'def' functions, adds unit tests at the end of the code encapsulated by comments. Also covers error cases in the unit tests.
- Keeps any mock data separate from the business logic. It should be easy to change to production data. Keeps the mock data outside 'def' functions.

### Reviewer

- Follows an approved plan.
- Reviews the code written by the engineer.
- Does not write code.
- Follows strict style rules for code review.
- Makes sure any 'def' functions have unit tests at the end of the code encapsulated by comments.
- Always finishes feedback with "code: APPROVED" or "code: REJECTED" depending on the feedback.
- If the code is incorrect, provides feedback to the engineer and addresses the engineer with "Dear engineer."
- Rejects code until there are no further improvement comments.
- The engineer will fix the code and output the code again.

### Executor

- Follows an approved plan.
- Runs the code written by the engineer.
- Does not write or review code.
- Executes the code and returns the result to the engineer.
- If the code execution fails, provides the error message to the engineer by saying "Dear engineer."
- Runs both the code and the unit tests; all should return the expected results.
- If the code execution is successful, returns the result to the planner by saying "Dear planner."

## Configuration

The project uses Anthropic's Sonnet LLM configuration. Ensure you have the appropriate API keys and configurations set up in your environment.

## Usage

1. **Planner**: Suggests a plan and assigns tasks to the engineer, reviewer, and executor.
2. **Engineer**: Writes the code based on the plan and asks the reviewer to check it.
3. **Reviewer**: Reviews the code and provides feedback.
4. **Engineer**: Implements the reviewer's suggestions and asks the executor to run the code.
5. **Executor**: Runs the code and returns the result.
