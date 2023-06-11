import os
import datetime
import time
import numpy as np
import pydicom as dicom
import argparse
from PIL import Image
from tqdm import tqdm
from configparser import ConfigParser
from feature_extractor import *
from utils import *


def get_all_image_paths(root_dir, ext, timing: bool = False) -> set:
    """
    Get all image paths in a directory, including subdirectories.

    Parameters:
    root_dir (str): Path of the directory to be searched.
    ext (str): File extension to be searched.

    Returns:
    set: A set of image paths.
    """
    t0 = time.time()
    image_paths = set()
    for dirpath, dirnames, filenames in tqdm(
        os.walk(root_dir), desc="Walking through directories"
    ):
        for filename in filenames:
            if filename.endswith(ext):
                image_paths.add(os.path.join(dirpath, filename))

    if timing is True:
        print(
            f"Time to walk through directories: {datetime.timedelta(seconds=time.time() - t0)}"
        )

    return image_paths


def file_batches_generator(directory, ext, batch_size) -> tuple:
    """
    Generator that yields batches of files from a directory and the total file count.

    Parameters:
    directory (str): Path of the directory to be searched.
    ext (str): File extension to be searched.
    batch_size (int): Size of the file batches to be returned.

    Yields:
    list: A list of file paths of size 'batch_size'.
    int: Total file count.
    """
    all_files = []
    for root, dirs, files in os.walk(directory):
        all_files.extend(
            [os.path.join(root, file) for file in files if file.endswith(ext)]
        )

    for i in range(0, len(all_files), batch_size):
        yield all_files[i : i + batch_size]


def load_data_batch(files, timing: bool = False) -> dict:
    """
    Load a batch of DICOM files into a dictionary.

    Parameters:
    files (list): A list of file paths to be loaded.

    Returns:
    dict: A dictionary where the keys are indices and the values are tuples of DICOM data and the file path.
    """
    t0 = time.time()
    data_dict = {}
    for index, file in tqdm(
        enumerate(files), desc="Loading IMAGE files", total=len(files)
    ):
        try:
            if file.endswith(".dcm") or file.endswith(".DCM") or file.endswith(""):
                data_dict[index] = [dicom.dcmread(file), file]
            else:
                with Image.open(file) as img:
                    data_dict[index] = [np.array(img), file]
        except Exception as e_:
            print(f"Error reading file {file}: {e_}")

    if timing is True:
        print(
            f"Time to load {len(files)} files: {datetime.timedelta(seconds=time.time() - t0)}"
        )

    return data_dict


def get_pixel_list(data, timing: bool = False) -> list:
    """
    Generate a list of pixel arrays from a dictionary of DICOM data.

    Parameters:
    data (dict): A dictionary of DICOM data.

    Returns:
    list: A list of pixel arrays.
    """
    t0 = time.time()
    imgs = []
    for key in tqdm(data, desc="Generating pixel arrays"):
        try:
            imgs.append(data[key][0].pixel_array)
        except Exception as e:
            print(f"Error reading file {data[key][1]}: {e}")

    if timing:
        print(
            f"Time to generate pixel arrays: {datetime.timedelta(seconds=time.time() - t0)}"
        )

    return imgs


def fivebhist_runner(
    data_root, final_file, log_dir, ext, batch_size, timing: bool = False
) -> None:
    """
    Run the 5-bin histogram feature extraction and bad image identification.

    Parameters:
    data_root (str): The root directory of the DICOM files.
    final_file_name (str): The name of the final text file containing paths to good images.
    """
    FEAT = "hist"
    NORM = "minmax"
    t0 = time.time()
    if not os.path.isdir(data_root):
        print("Provided data root directory does not exist.")
        return

    # The set of bad image paths
    bad_paths = set()

    print("Running 5-BHIST Stage 1...")

    # Get all image paths at the start
    all_paths = get_all_image_paths(data_root, ext, timing=timing)
    total_files = len(all_paths)

    file_batches_gen = file_batches_generator(data_root, ext, batch_size)

    for file_batch in file_batches_gen:
        data_dict = load_data_batch(file_batch, timing=timing)
        data_imgs = get_pixel_list(data_dict, timing=timing)

        five_b_hist = Features.get_features(
            data_imgs, feature_type=FEAT, norm_type=NORM, bins=5, timing=timing
        )

        print("Finding bad images...")
        for i, binary in enumerate(five_b_hist):
            if binary[4] > 15000 or binary[1] < 1000:
                print(i, binary)
                bad_paths.add(data_dict[i][1])

    print(f"Total files: {total_files}")

    date_and_time = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    file_name_bad_paths = f"{date_and_time}_bad_paths.txt"

    # check if log directory exists and create it if it doesn't
    if not os.path.isdir(log_dir):
        os.mkdir(log_dir)

    with open(os.path.join(log_dir, file_name_bad_paths), "w") as f:
        f.write("\n".join(list(bad_paths)))

    # Get the set of good image paths by subtracting the set of bad image paths from the set of all image paths
    good_paths = list(all_paths - bad_paths)

    with open(os.path.join(log_dir, final_file), "w") as f:
        f.write("\n".join(good_paths))

    print(f"number of bad images found: {len(bad_paths)}")
    print(f"number of good images found: {len(good_paths)}")

    if timing is True:
        print(
            f"Total time to run feature extraction: {datetime.timedelta(seconds=time.time() - t0)}"
        )


# In the main section of your script, you can call this method at the beginning:
if __name__ == "__main__":
    """
    Main entry point of the program. Parses command-line arguments, reads the config file,
    overwrites config values if command line arguments are provided, and then runs the 5BHIST algorithm.

    Supports the following command-line arguments:
        --data_root: The root directory of the DICOM files.
        --final_file: The name of the final text file containing paths to good images.
    """
    # read the config file
    config = ConfigParser()
    config.read("config.ini")

    parser = argparse.ArgumentParser(description="Image feature extraction task.")
    parser.add_argument(
        "--data_root",
        type=str,
        default=config["5BHIST"]["data_root"],
        help="Root directory of the data.",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default=config["5BHIST"]["log_dir"],
        help="Directory to save the log files.",
    )
    parser.add_argument(
        "--final_file",
        type=str,
        default=config["5BHIST"]["final_file"],
        help="Name of the final text file containing paths to good images.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=config["5BHIST"]["batch_size"],
        help="Number of files to load at a time.",
    )
    parser.add_argument(
        "--ext",
        type=str,
        default=config["5BHIST"]["ext"],
        help="File extension of the DICOM files.",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        default=config.getboolean("5BHIST", "timing"),
        help="Whether to time the feature extraction process.",
    )

    args = parser.parse_args()

    validate_inputs(**vars(args))

    print_properties("5BHIST Runner", **vars(args))

    try:
        fivebhist_runner(
            args.data_root,
            args.final_file,
            args.log_dir,
            args.ext,
            args.batch_size,
            args.timing,
        )
    except Exception as e:
        print(f"An error occurred: {e}")
