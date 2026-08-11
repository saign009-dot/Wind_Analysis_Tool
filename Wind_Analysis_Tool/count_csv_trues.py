import argparse
from collections import Counter
import csv
from pathlib import Path


def row_value(row, header_map, *column_names):
    for column_name in column_names:
        index = header_map.get(column_name)
        if index is not None and index < len(row):
            return row[index].strip()
    return "unknown"


def count_values(csv_path):
    true_count = 0
    false_count = 0
    non_empty_count = 0
    true_rows = []

    with csv_path.open(mode="r", newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        header = next(reader, None)
        if header is None:
            return true_count, false_count, non_empty_count, true_rows

        header_map = {
            column.strip().lower(): index for index, column in enumerate(header)
        }

        for row_number, row in enumerate([header], start=1):
            for column_index, value in enumerate(row):
                value = value.strip().lower()
                if not value:
                    continue

                non_empty_count += 1
                if value == "true":
                    true_count += 1
                    true_rows.append(
                        {
                            "row": row_number,
                            "column": (
                                header[column_index]
                                if column_index < len(header)
                                else f"column_{column_index + 1}"
                            ),
                            "dataset": row_value(row, header_map, "dataset"),
                            "scenario": row_value(row, header_map, "scenario"),
                            "period": row_value(
                                row,
                                header_map,
                                "period",
                                "time_period",
                                "time period",
                            ),
                            "percentile": row_value(row, header_map, "percentile"),
                        }
                    )
                elif value == "false":
                    false_count += 1

        for row_number, row in enumerate(reader, start=2):
            for column_index, value in enumerate(row):
                value = value.strip().lower()
                if not value:
                    continue

                non_empty_count += 1
                if value == "true":
                    true_count += 1
                    true_rows.append(
                        {
                            "row": row_number,
                            "column": (
                                header[column_index]
                                if column_index < len(header)
                                else f"column_{column_index + 1}"
                            ),
                            "dataset": row_value(row, header_map, "dataset"),
                            "scenario": row_value(row, header_map, "scenario"),
                            "period": row_value(
                                row,
                                header_map,
                                "period",
                                "time_period",
                                "time period",
                            ),
                            "percentile": row_value(row, header_map, "percentile"),
                        }
                    )
                elif value == "false":
                    false_count += 1

    return true_count, false_count, non_empty_count, true_rows


def percent(part, total):
    if total == 0:
        return 0.0
    return part / total * 100


def main():
    parser = argparse.ArgumentParser(
        description="Count TRUE values across CSV files and calculate their percentage."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Folder to search for CSV files. Defaults to the current folder.",
    )
    parser.add_argument(
        "--all-cells",
        action="store_true",
        help="Calculate percentage using all non-empty cells instead of only TRUE/FALSE cells.",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    csv_files = sorted(folder.rglob("*.csv"))

    total_true = 0
    total_false = 0
    total_non_empty = 0
    true_context_counts = Counter()

    for csv_file in csv_files:
        true_count, false_count, non_empty_count, true_rows = count_values(csv_file)
        boolean_count = true_count + false_count
        denominator = non_empty_count if args.all_cells else boolean_count

        total_true += true_count
        total_false += false_count
        total_non_empty += non_empty_count
        for true_row in true_rows:
            true_context_counts[(true_row["scenario"], true_row["period"])] += 1

        print(f"{csv_file}")
        print(f"  TRUE values: {true_count}")
        print(f"  FALSE values: {false_count}")
        print(f"  TRUE percentage: {percent(true_count, denominator):.2f}%")
        if true_rows:
            print("  TRUE details:")
            for true_row in true_rows:
                print(
                    "    "
                    f"row {true_row['row']}, {true_row['column']}: "
                    f"scenario={true_row['scenario']}, "
                    f"period={true_row['period']}, "
                    f"dataset={true_row['dataset']}, "
                    f"percentile={true_row['percentile']}"
                )

    total_boolean = total_true + total_false
    total_denominator = total_non_empty if args.all_cells else total_boolean

    print()
    print("Overall")
    print(f"  CSV files checked: {len(csv_files)}")
    print(f"  TRUE values: {total_true}")
    print(f"  FALSE values: {total_false}")
    print(f"  Non-empty cells: {total_non_empty}")
    print(f"  TRUE percentage: {percent(total_true, total_denominator):.2f}%")
    if true_context_counts:
        print()
        print("Overall TRUE values by scenario and period")
        for (scenario, period), count in sorted(true_context_counts.items()):
            print(f"  {scenario}, {period}: {count}")


if __name__ == "__main__":
    main()
