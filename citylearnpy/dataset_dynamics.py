"""Build portable CityLearn temperature dynamics from an ingested package."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from citylearn.dynamics import LSTMDynamics

MIN_HOURS = 72
MAX_SAMPLES_PER_SPLIT = 20000


def sequence_batch(normalized, indices, lookback, temperature):
    offsets = np.arange(-lookback + 1, 1)
    window = normalized[indices[:, None] + offsets[None, :]].copy()
    window[:, :, temperature] = normalized[indices[:, None] + offsets[None, :] - 1, temperature]
    return torch.from_numpy(window), torch.from_numpy(normalized[indices, temperature].reshape(-1, 1).copy())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def fill_missing(target, defaults):
    for name, value in defaults.items():
        if name not in target:
            target[name] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(target[name], dict):
            fill_missing(target[name], value)


def local_file(directory, name):
    path = (directory / name).resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise ValueError('Invalid or missing package file: ' + str(name))
    return path


def features(directory, building, names):
    energy = pd.read_csv(local_file(directory, building['energy_simulation']))
    weather = pd.read_csv(local_file(directory, building['weather']))
    if len(energy) != len(weather) or len(energy) < MIN_HOURS:
        raise ValueError('PTH generation requires at least 72 aligned hourly records per building')
    values = []
    for name in names:
        base = name.rsplit('_', 1)[0] if name.endswith(('_sin', '_cos')) else name
        frame = energy if base in energy else weather
        if base not in frame:
            raise ValueError('Missing dynamics input: ' + base)
        data = pd.to_numeric(frame[base], errors='coerce').to_numpy(dtype=np.float64)
        if not np.isfinite(data).all():
            raise ValueError('Invalid dynamics input: ' + base)
        if base != name:
            period = {'month': 12, 'hour': 24, 'day_type': 8}[base]
            data = (np.sin if name.endswith('_sin') else np.cos)(2 * np.pi * data / period)
        values.append(data)
    return np.stack(values, axis=1)


def prepare_package(directory, template):
    directory, template = Path(directory), Path(template)
    schema, defaults = read(directory / 'schema.json'), read(template / 'schema.json')
    # Equipment, measurements, and selected time bounds belong to this package.
    retained = {k: schema[k] for k in ('buildings', 'simulation_start_time_step', 'simulation_end_time_step')}
    schema = copy.deepcopy(defaults)
    schema.update(retained)
    schema['root_directory'] = None
    prototype = next(iter(defaults['buildings'].values()))
    for key, building in schema['buildings'].items():
        if not key.replace('_', '').isalnum():
            raise ValueError('Invalid building key')
        source_prototype = defaults['buildings'].get(key, prototype)
        for field in ('type', 'include', 'power_outage'):
            if field in source_prototype:
                building[field] = copy.deepcopy(source_prototype[field])
        # Keep the imported equipment set; only fill missing parameters for devices it has.
        for equipment, source_config in source_prototype.items():
            if equipment in building and isinstance(source_config, dict) and isinstance(building[equipment], dict):
                fill_missing(building[equipment], source_config)
        building['inactive_actions'] = [name for name, signal in schema['actions'].items()
                                        if signal.get('active') and name not in building]
        building['inactive_observations'] = []
        for name, signal in schema['observations'].items():
            equipment = None
            if name.endswith('_soc'):
                equipment = name[:-4]
            elif name.endswith('_device_efficiency'):
                equipment = name[:-11]
            elif name.endswith('_storage_electricity_consumption'):
                equipment = name[:-24]
            if equipment and equipment not in building:
                building['inactive_observations'].append(name)
        dynamics = copy.deepcopy(source_prototype['dynamics'])
        attrs = dynamics['attributes']
        attrs['filename'] = key + '.pth'
        raw = features(directory, building, attrs['input_observation_names'])
        train_end = int((len(raw) - attrs['lookback']) * .7) + attrs['lookback']
        low, high = raw[:train_end].min(axis=0), raw[:train_end].max(axis=0)
        high = np.where(high - low < 1.e-6, low + 1., high)
        attrs['input_normalization_minimum'] = low.tolist()
        attrs['input_normalization_maximum'] = high.tolist()
        building['dynamics'] = dynamics
    write(directory / 'schema.json', schema)
    return {'modelGenerationRequired': True, 'buildingCount': len(schema['buildings']),
            'minimumHours': MIN_HOURS, 'defaultsSource': template.name}


def train_building(directory, key, building, epochs, seed):
    torch.manual_seed(seed)
    attrs = copy.deepcopy(building['dynamics']['attributes'])
    raw = features(directory, building, attrs['input_observation_names'])
    low, high = np.array(attrs['input_normalization_minimum']), np.array(attrs['input_normalization_maximum'])
    normalized = ((raw - low) / (high - low)).astype(np.float32)
    lookback = attrs['lookback']
    temperature = attrs['input_observation_names'].index('indoor_dry_bulb_temperature')
    # The chronological split precedes deterministic sampling to bound memory on large releases.
    sample_count = len(raw) - lookback
    first, second = int(sample_count * .7), int(sample_count * .85)
    spans = (np.arange(lookback, lookback + first),
             np.arange(lookback + first, lookback + second),
             np.arange(lookback + second, len(raw)))
    def sample(indices):
        if len(indices) > MAX_SAMPLES_PER_SPLIT:
            indices = indices[np.linspace(0, len(indices) - 1, MAX_SAMPLES_PER_SPLIT, dtype=np.int64)]
        return indices
    train_indices, validation_indices, test_indices = map(sample, spans)
    def batch(indices):
        return sequence_batch(normalized, indices, lookback, temperature)
    filename = attrs.pop('filename')
    model = LSTMDynamics(filepath=str(directory / filename), **attrs)
    optimizer = torch.optim.Adam(model.parameters(), lr=.008)
    batch_size = min(168, len(train_indices))
    best_loss, best, best_epoch = float('inf'), None, 0

    def prediction(batch):
        return model(batch, model.init_hidden(len(batch)))[0]

    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(train_indices)).numpy()
        for start in range(0, len(train_indices), batch_size):
            indices = train_indices[order[start:start + batch_size]]
            x, y = batch(indices)
            loss = torch.nn.functional.mse_loss(prediction(x), y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            x, y = batch(validation_indices)
            validation = torch.nn.functional.mse_loss(prediction(x), y).item()
        if not np.isfinite(validation):
            raise ValueError('Non-finite validation loss: ' + key)
        if validation < best_loss:
            best_loss, best_epoch = validation, epoch + 1
            best = copy.deepcopy(model.state_dict())
    model.load_state_dict(best)
    model.eval()
    with torch.no_grad():
        errors = []
        for start in range(0, len(test_indices), batch_size):
            x, y = batch(test_indices[start:start + batch_size])
            errors.append((prediction(x) - y).numpy())
        error = np.concatenate(errors) * (high[temperature] - low[temperature])
    torch.save({'model_state_dict': best}, directory / filename)
    return {'building': key, 'filename': filename, 'epochs': epochs, 'bestEpoch': best_epoch,
            'seed': seed, 'trainSamples': len(train_indices), 'validationSamples': len(validation_indices),
            'testSamples': len(test_indices), 'validationMse': best_loss,
            'testMaeC': float(np.abs(error).mean()), 'testRmseC': float(np.sqrt((error ** 2).mean()))}


def finalize_manifest(directory, reports):
    manifest = read(directory / 'manifest.json')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(directory.iterdir()) if p.is_file() and p.name != 'manifest.json'}
    manifest.update(profile='community-ol1-defaults-generated-dynamics', thermalModel='LSTMDynamics', files=hashes,
                    contentHash=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                    modelAssets=[dict(report, sha256=hashes[report['filename']]) for report in reports],
                    modelGeneration={'method': 'supervised LSTM; chronological target-time split 70/15/15',
                                     'normalization': 'training prefix only',
                    'sampleCapPerSplit': MAX_SAMPLES_PER_SPLIT,
                    'limitation': 'One-step historical fit does not validate counterfactual control or long-horizon accuracy'})
    manifest.setdefault('publicationSummary', {}).update(thermalModel='LSTMDynamics', modelGenerationRequired=False)
    write(directory / 'manifest.json', manifest)


def generate_package(directory, epochs=144, progress=None):
    directory = Path(directory)
    schema = read(directory / 'schema.json')
    torch.set_num_threads(1)
    reports = []
    for index, (key, building) in enumerate(schema['buildings'].items()):
        if progress:
            progress(index, len(schema['buildings']))
        reports.append(train_building(directory, key, building, epochs, 2023 + index))
    write(directory / 'dynamics_training_report.json', {'status': 'generated', 'buildings': reports})
    finalize_manifest(directory, reports)
    return {'status': 'generated', 'buildings': reports}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    result = prepare_package(args.directory, args.template)
    if not args.preview:
        result = generate_package(args.directory, progress=lambda completed, total: print(
            json.dumps({'stage': 'generating_models', 'completed': completed, 'total': total}), flush=True))
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
