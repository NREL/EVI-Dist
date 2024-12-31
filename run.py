import subprocess

def run_command(command):
    try:
        # Run the command using subprocess
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Specify the command to run
    command_to_run = "panel serve dashboard/app.py --port 5007 --show --autoreload --static-dirs /docs=docs"

    # Call the function to run the command
    run_command(command_to_run)
