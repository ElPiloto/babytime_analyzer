from datetime import datetime, timedelta
import glob
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sn
import pdb
import os

# TODO(piloto): look at predicting amount of awake time at night vs. nap properties
# TODO(piloto): look at gap between last nap and bedtime

try:
  plt.interactive(True)
except:
  pass

# 2020-01-23 11:35 PM
_DATETIME_FORMAT = '%Y-%m-%d %I:%M %p'
_END_OF_RECORD_DELIMITER = '===================='


def list_files(glob_pattern='activity*.txt'):
  return glob.glob(glob_pattern)

def parse_datetimes(line):
  """Parse date in format: `START_TIME [~ END_TIME]`"""
  parsed = {}
  datetimes = line.split('~')
  try:
    for i, dt in enumerate(datetimes):
      datetimes[i] = datetime.strptime(dt.strip(), _DATETIME_FORMAT)
  except:
    raise ValueError('Expected to see a datetime as first entry in new record formatted as: `{}`, but found: {}'.format(dt))
  parsed['start'] = datetimes[0]
  if len(datetimes) == 2:
    parsed['end'] = datetimes[1]
  else:
    parsed['end' ] = datetimes[0]
  return parsed

def parse_generic(line):
  if line == _END_OF_RECORD_DELIMITER:
    return {}

  k, v = line.split(': ')
  return {k: v}

def clean_key(k):
  k = k.strip()
  k = k.lower()
  k = k.replace(' ', '_')
  return k

def maybe_convert_sleep(k, v):
  if k == 'type':
    v = v.lower()
    if 'sleep' in v:
      if 'night' in v:
        v = 'sleep'
      else:
        v = 'nap'
  return k, v

def maybe_convert_duration(k, v):
  if k == 'duration':
    try:
      v = float(v.strip().split(' (min)')[0])
    except:
      raise ValueError('Expected to parse duration in format: "# (mins)", but received: {}'.format(v))
  return k, v

def maybe_convert_amount(k, v):
  if type(v) == str and 'ml' in v:
    try:
      v = float(v.strip().split(' (ml)')[0])
    except:
      raise ValueError('Expected to parse amount in format: "# (mins)", but received: {}'.format(v))
  return k, v

def sanitize_fields(fields):
  sanitized = {}
  for k, v in fields.items():
    new_k = clean_key(k)
    if type(v) is str:
      new_v = v.strip()
    else:
      new_v = v
    new_k, new_v = maybe_convert_sleep(new_k, new_v)
    new_k, new_v = maybe_convert_duration(new_k, new_v)
    new_k, new_v = maybe_convert_amount(new_k, new_v)
    sanitized[new_k] = new_v
  return sanitized

def sanitize_record(d):
  # add duration to everything
  if 'duration' not in d:
    duration_mins = d['end'] - d['start']
    duration_mins = duration_mins.total_seconds() / 60.
    d['duration'] = duration_mins
  #pdb.set_trace()

def parse_files(files=None):
  data = []
  for f in files:
    with open(f, mode='r') as fp:
      line = fp.readline().strip()
      new_record = True
      while line:
        print('parsing: {}'.format(line))
        # special handling of datetimes
        if new_record:
          record = {}
          fields = parse_datetimes(line)
          new_record = False
        else:
          fields = parse_generic(line)

        # if we didn't hit the end of a record
        if fields:
          fields = sanitize_fields(fields)
          record.update(fields)
          #pdb.set_trace()
        else:
          #pdb.set_trace()
          sanitize_record(record)
          data.append(record)
          new_record = True
        line = fp.readline().strip()
  return data

def main():
  files = list_files()
  # list of dicts containing fields for each record
  data = parse_files(files)
  df = pd.DataFrame(data)
  sleep_by_days(df)

def cleanup_naps(naps):
  print('Cleaning up nap')
  print('=================')
  # Remove any naps which were longer than 6 hours, clearly that's not a nap.
  print('Num naps before dropping anything: {}'.format(len(naps)))
  naps = naps.drop(naps[(naps.type == 'nap') & (naps.duration > 6*60)].index)
  print('Num naps after dropping long naps: {}'.format(len(naps)))
  naps = naps.drop(naps[naps.duration == 0].index)
  print('Num sleeps after dropping days with 0 naps: {}'.format(len(naps)))
  print('\n')
  return naps

def cleanup_sleeps(sleeps):
  print('Cleaning up sleep')
  print('=================')
  invalid_sleep_dates = [
      # Entered monolithically instead of based on wake ups
      '2019-12-19',
      '2019-12-20',
      '2019-12-21',
      '2019-12-22',
      # flights US <--> UK
      '2019-12-14',
      '2019-12-28',
      ]
  # Remove some sleep data that was entered as a long chunk instead of detailed information:
  print('Num sleeps before dropping anything: {}'.format(len(sleeps)))
  for d in invalid_sleep_dates:
    sleeps = sleeps.drop(sleeps.loc[d].index)
  print('Num sleeps after dropping invalid input sleep dates: {}'.format(len(sleeps)))
  sleeps = sleeps.drop(sleeps[sleeps.duration == 0].index)
  print('Num sleeps after dropping days with 0 sleep: {}'.format(len(sleeps)))
  print('\n')
  return sleeps


def sleep_by_days(df):
  # this means that any sleep (but not naps) that happen up until 8 A.M. will get counted as the day before

  sleeps = df.copy()
  sleeps['modified_start'] = sleeps['start'] 
  #sleeps[sleeps['type'] == 'sleep']['modified_start'] += timedelta(hours=-8)

  sleeps.loc[sleeps['type'] == 'sleep', 'modified_start'] = sleeps.loc[sleeps['type'] == 'sleep', 'modified_start'] + timedelta(hours=-8)
  #data.loc[data['name'] == 'fred', 'A'] = 0
  sleeps = sleeps.set_index('modified_start')
  sleeps = sleeps.sort_values(by='modified_start')

  # first let's get all naps by day
  naps = df.set_index('start')
  naps = naps[naps.type.eq('nap')]
  naps = naps.sort_values(by='start')

  naps = cleanup_naps(naps)

  sleeps = sleeps[sleeps.type.eq('sleep')]
  sleeps = cleanup_sleeps(sleeps)

  def nonempty(x, method='sum'):
    if not x.empty:
      # there has to be a better way to do this?
      if method == 'sum':
        return x.sum()
      elif method == 'count':
        return x.count()
      elif method == 'max':
        return x.max()
      elif method == 'min':
        return x.min()

  #total_naps = naps.resample('D').duration.sum()
  #total_sleep = sleeps.resample('D').duration.sum()

  total_naps = naps.resample('D').duration.apply(nonempty)
  total_sleep = sleeps.resample('D').duration.apply(nonempty)

  max_naps = naps.resample('D').duration.max()
  max_sleep = sleeps.resample('D').duration.max()

  count_naps = naps.resample('D').duration.count()
  count_sleep = sleeps.resample('D').duration.count()
  # plt.plot_date(total_naps.keys(), total_naps.values)
  # plt.plot_date(total_sleep total_sleep.values)

  # first let's plot a histogram of the distribution of nap durations
  plt.subplot(5, 4, 1)
  plt.hist(sleeps['duration']/60., label='Individual sleep durations')
  plt.title('Individual sleep durations')
  plt.subplot(5, 4, 2)
  plt.hist(naps['duration']/60., label='Individual nap durations')
  plt.title('Individual nap durations')

  # plot histogram of total sleep/nap durations
  plt.subplot(5, 4, 3)
  plt.hist(total_sleep.values/60., label='Total sleep durations')
  plt.title('Total sleep durations')
  plt.subplot(5, 4, 4)
  plt.hist(total_naps.values/60., label='Total nap durations')
  plt.title('Total nap durations')

  plt.subplot(5, 4, 5)
  plt.plot_date(total_naps.keys(), total_naps.values/60., label='Naps')
  plt.plot_date(total_sleep.keys(), total_sleep.values/60., label='Sleeps')
  plt.xticks(rotation=90)
  #plt.legend()


  plot10 = np.copy(max_naps.values/60.)
  # 12
  plt.subplot(5, 4, 10)
  #plt.scatter(max_naps.values/60., total_sleep.values/60.)
  sn.regplot(max_naps.values/60., total_sleep.values/60., robust=True)
  plt.xlabel('Max Nap Length')
  plt.ylabel('Total Sleep')

  plt.subplot(5, 4, 11)
  plt.scatter(count_naps.values, total_sleep.values/60.)
  plt.xlabel('Num Naps')
  plt.ylabel('Total Sleep')

  plot12 = np.copy(max_naps.values/60.)
  # 3.
  plt.subplot(5, 4, 12)
  #plt.scatter(max_naps.values/60., max_sleep.values/60.)
  sn.regplot(max_naps.values/60., max_sleep.values/60., robust=True)
  plt.xlabel('Max Nap Length')
  plt.ylabel('Max Sleep Length')

  # 12
  plot13 = np.copy(max_naps.values/60.)
  plt.subplot(5, 4, 13)
  #plt.scatter(max_naps.values/60., count_sleep.values)
  sn.regplot(max_naps.values/60., count_sleep.values, robust=True)
  plt.xlabel('Max Nap Length')
  plt.ylabel('Num Sleeps')

  #
  plt.subplot(5, 4, 18)
  plt.scatter(total_naps.values/60., total_sleep.values/60.)
  plt.xlabel('Total Nap')
  plt.ylabel('Total Sleep')

  plt.subplot(5, 4, 20)
  #plt.scatter(total_naps.values/60., count_sleep.values)
  sn.regplot(total_naps.values/60., count_sleep.values, robust=True)
  plt.xlabel('Total Nap')
  plt.ylabel('Num Sleeps')


  plt.show()
  pdb.set_trace()


if __name__ == '__main__':
  main()
  

