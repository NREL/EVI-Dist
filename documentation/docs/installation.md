# Installation 

The recommended way to use EVI-DiST is through the interactive dashboard. After setting up the environment, users can interact with EVI-DiST from their web browser without having to run the code in any IDE. The command line interface and Python interactive notebook examples could be added in future releases.

## Setup
EVI-DiST requires the use of the Anaconda Python distribution. Users who do not use Anaconda will have to install the required packages manually. Refer to `EVI-Dist/environment.yaml` for the required packages.

1. After cloning or forking the repository, in the root directory `EVI-Dist/`, run the following command and follow the command line prompts to create a conda environment:
```sh
conda env create -f ./environment.yaml
```

2. The created environment will be named `dist`. To activate the conda environment enter the following command:
```sh
conda activate dist
```

3. If all packages successfully installed, see the __Run Instructions__ for how to run an EVI-EnSite simulation.

## Run Instructions
If the installation was successful, the user can immediately run the following code in the `EVI-Dist/` directory to start EVI-Dist. EVI-Dist's dashboard interface will open in the default browser as shown in Figure below.
```sh
python run.py
```

![Alt text](./img/welcome.png "EVI-DiST Welcome Page")