# Automated GPU driver installation testing

The current version of automated testing is meant to be run
manually on local developer machine. Required steps:

1. Use `gcloud auth application-default login` to configure
   account you want to use for testing.
2. (optional) Use `gcloud config set project $PROJECT` to
   specify a project you want to use for testing.
3. Install required Python packages `pip install -Ur requirements.txt`
4. Run test using `pytest` command. You can speed up the 
   process by using parallel execution with 
   `pytest --workers 1 --tests-per-worker 10`. Remember to use only one
  process, as the tests use thread semaphores to make sure they don't exceed
  GPU quota


Note: The VMs created for this test don't have external IP
addresses assigned, so it's required for the project
they are created in to have Cloud NAT configured for the
default VPC Network. Without it, the instances won't be
able to download necessary drivers.