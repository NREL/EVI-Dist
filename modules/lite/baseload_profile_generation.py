import pandas as pd
import os
from datetime import datetime, timedelta
import pytz

def generate_upsampled_baseload(df, month, file_name, timezone):
    # Convert the 'time' column to datetime format
    print("Generating baseload profiles...")
    file_path_to_save = os.getcwd() + "/data/temp/" + file_name + ".csv"

    df['time'] = pd.to_datetime(df['time'])
    #df['time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert('America/Denver')
    df['time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert(timezone)

    # Extract the year from the first row of the DataFrame
    year = df['time'].dt.year.iloc[0]

    # Get the first day of the given month and year
    start_date = datetime(year=year, month=month, day=1)

    # Find the first Monday of the month
    first_monday = start_date + timedelta(days=(7 - start_date.weekday()) % 7)

    # Find the first Sunday of the month
    first_sunday = first_monday + timedelta(days=6)

    # Convert first_monday and first_sunday to timezone-aware datetime objects
    #timezone = pytz.timezone('America/Denver')
    timezone = pytz.timezone(timezone)
    first_monday = timezone.localize(first_monday)
    first_sunday = timezone.localize(first_sunday)

    # Filter rows between the first Monday and the first Sunday
    filtered_df = df[(df['time'] >= first_monday) & (df['time'] < first_sunday + timedelta(days=1))]

    # Generate 1-minute resolution timestamps within the selected range
    new_times = pd.date_range(start=first_monday, end=first_sunday + timedelta(days=1), freq='1min')
    
    # Create a DataFrame with the new timestamps
    new_times_df = pd.DataFrame({'time': new_times})

    # Merge the new timestamps DataFrame with the filtered DataFrame
    upsampled_df = new_times_df.merge(filtered_df, how='left', on='time')

    # Forward fill missing values
    upsampled_df = upsampled_df.ffill()

    # Create the 'date' column with the format '1/31/2023 0:00'
    upsampled_df['date'] = upsampled_df['time'].dt.strftime('%m/%d/%Y %H:%M')

    # Extract time as timedelta for 'time' column
    upsampled_df['time'] = upsampled_df['time'].dt.time

    # Calculate the day column starting from 1
    upsampled_df['day'] = (upsampled_df.index // (24 * 60) + 1).astype(int)

    # Reorder columns
    upsampled_df = upsampled_df[['day', 'time', 'date'] + [col for col in df.columns if col != 'time']]

    # Reduce the resoultion to float16 (experimental)
    upsampled_df.iloc[:, 4:] = upsampled_df.iloc[:, 4:].astype('float16')

    # Downsample
    removed_last_sample_df = upsampled_df.iloc[:-1:1] # TODO: This needs to work with any AMI data. There is a need to make sure the downsampled baseline profile always matches the ev profile length-wise. 

    # Save
    removed_last_sample_df.to_csv(file_path_to_save, index=True)

    print("Completed!")
