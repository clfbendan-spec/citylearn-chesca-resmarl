"""Download all built-in CityLearn datasets into the package cache."""
import time

from citylearn.data import DataSet

MAX_RETRIES = 3
RETRY_DELAY_SEC = 5


def download_dataset(ds: DataSet, name: str) -> str:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return ds.get_dataset(name)
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                print(f"  retry {attempt}/{MAX_RETRIES - 1} after error: {exc}", flush=True)
                time.sleep(RETRY_DELAY_SEC)
    raise last_error


def main() -> None:
    ds = DataSet()
    names = ds.get_dataset_names()
    print(f"Cache directory: {ds.cache_directory}")
    print(f"Datasets to fetch: {len(names)}\n")

    ok, failed = [], []

    for i, name in enumerate(names, 1):
        print(f"[{i}/{len(names)}] {name} ...", flush=True)
        try:
            schema_path = download_dataset(ds, name)
            print(f"  -> {schema_path}")
            ok.append(name)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            failed.append((name, str(exc)))

    print("\n--- Summary ---")
    print(f"Downloaded/verified: {len(ok)}")
    if failed:
        print(f"Failed: {len(failed)}")
        for name, err in failed:
            print(f"  - {name}: {err}")
    else:
        print("All datasets are in cache.")


if __name__ == "__main__":
    main()
