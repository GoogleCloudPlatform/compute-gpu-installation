# Automated GPU driver installation testing

The current version of automated testing is meant to be run
manually on the local developer machine. Required steps:

1. Use `gcloud auth application-default login` and `gcloud auth login` 
   to configure the account you want to use for testing.
2. Use `gcloud config set project $PROJECT` to
   specify a project you want to use for testing.
3. Install required Python packages `pip install -Ur requirements.txt`
4. Run tests using `pytest` command in the `/linux/cuda_installer` directory. You can 
   speed up the process by using parallel execution with 
   `pytest -n 8`. 
