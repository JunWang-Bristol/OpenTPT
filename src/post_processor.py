import pandas
import sys
import json
import math
import matplotlib.pyplot as plt
import statistics
import numpy


class PostProcessor():
    def get_voltage_change_indexes(self, data, label, maximum_change_window=100):
        data["diff"] = data[label].diff()
        maximum_diff_peak = data["diff"].max()
        data["diff"] = data["diff"].apply(lambda row: 0 if (row < maximum_diff_peak * 0.3) else 1)
        change_indexes = data[data["diff"] > 0].index
        change_indexes_diff = change_indexes.diff()
        change_indexes = [int(change_indexes[i]) for i, x in enumerate(change_indexes_diff) if x > maximum_change_window]
        change_indexes.insert(0, 0)
        change_indexes.append(data.index[-1])
        return change_indexes

    def get_current_change_indexes(self, data, label, maximum_change_window=2000, sensitivity=3):
        change_indexes = [0]
        change_peak_values = [data[label].iloc[0]]
        change_average_values = [data[label].iloc[0]]
        for window_index in range(0, len(data.index), int(maximum_change_window / sensitivity)):
            chunk = data.iloc[window_index: window_index + maximum_change_window][label]
            chunk_minimum = chunk.min()
            chunk_maximum = chunk.max()
            first_10_percent = chunk.iloc[0:int(maximum_change_window * 0.1)].values
            last_10_percent = chunk.iloc[-int(maximum_change_window * 0.1) - 1:-1].values
            if (chunk_minimum not in first_10_percent and chunk_maximum not in first_10_percent) or \
               (chunk_minimum not in last_10_percent and chunk_maximum not in last_10_percent):
                if len(change_peak_values) == 0 or (chunk_maximum != change_peak_values[-1] and chunk_minimum != change_peak_values[-1]):
                    if chunk_minimum not in first_10_percent and chunk_minimum not in last_10_percent:
                        change_values_indexes = chunk[chunk == chunk_minimum].index
                        peak_index = int(sum(change_values_indexes) / len(change_values_indexes))
                        change_indexes.append(peak_index)
                        change_peak_values.append(chunk_minimum)
                        peak_value = float(chunk.loc[peak_index - 20:peak_index + 20 + 1].mean())
                        change_average_values.append(peak_value)
                    if chunk_maximum not in first_10_percent and chunk_maximum not in last_10_percent:
                        change_values_indexes = chunk[chunk == chunk_maximum].index
                        peak_index = int(sum(change_values_indexes) / len(change_values_indexes))
                        change_indexes.append(peak_index)
                        change_peak_values.append(chunk_maximum)
                        peak_value = float(chunk.loc[peak_index - 20:peak_index + 20 + 1].mean())
                        change_average_values.append(peak_value)

        change_indexes.append(data.index[-1])
        change_average_values.append(data[label].iloc[-1])

        for i in range(len(change_indexes) - 1):
            index = change_indexes[i]
            next_index = change_indexes[i + 1]

            if index > next_index:
                change_indexes[i] = next_index
                change_indexes[i + 1] = index
                average_value = change_average_values[i]
                next_average_value = change_average_values[i + 1]
                change_average_values[i + 1] = average_value
                change_average_values[i] = next_average_value

        return change_indexes, change_average_values

    def post_process_voltage(self, data, label, maximum_change_window=100, external_change_indexes=None):
        if external_change_indexes is None:
            change_indexes = self.get_voltage_change_indexes(data, label, maximum_change_window)
        else:
            change_indexes = external_change_indexes

        data["clean"] = 0.0

        for chunk_index in range(len(change_indexes) - 1):
            chunk = data.iloc[change_indexes[chunk_index]: change_indexes[chunk_index + 1]]
            # voltage_clean_value = float(chunk[label].round(2).mode().iloc[0])
            voltage_clean_value = float(chunk[label].round(2).mean())
            data.loc[change_indexes[chunk_index]: change_indexes[chunk_index + 1], "clean"] = voltage_clean_value

        return data["clean"]

    def post_process_current(self, data, label, maximum_change_window=2000, sensitivity=3, external_change_indexes_and_values=None):
        if external_change_indexes_and_values is None:
            change_indexes, change_values = self.get_current_change_indexes(data, label, maximum_change_window, sensitivity)
        else:
            change_indexes, change_values = external_change_indexes_and_values

        data["clean"] = 0.0

        # change_values = [data[label].loc[x] for x in change_indexes]
        # change_values.append(data[label].iloc[-1])
        for chunk_index in range(len(change_indexes) - 1):
            start = change_values[chunk_index]
            stop = change_values[chunk_index + 1]
            number_points = change_indexes[chunk_index + 1] - change_indexes[chunk_index]
            
            # Skip if no points to interpolate or duplicate indexes
            if number_points <= 0:
                continue
                
            step = (stop - start) / (number_points + 1)
            
            # Handle case where step is zero (start == stop)
            if step == 0:
                values = numpy.full(number_points + 1, start)
            else:
                values = numpy.arange(start, stop, step)
            
            print("chunk_index")
            print(chunk_index)
            print(change_indexes[chunk_index])
            print(change_indexes[chunk_index + 1])
            data.loc[change_indexes[chunk_index]: change_indexes[chunk_index + 1], "clean"] = values[0: len(data.loc[change_indexes[chunk_index]: change_indexes[chunk_index + 1]].index)]

        return data["clean"]

    def analyze_loops(self, data):
        change_indexes, change_values = self.get_current_change_indexes(data, "Current")
        print(change_indexes)

        data["Current Clean"] = self.post_process_current(data, "Current", external_change_indexes_and_values=(change_indexes, change_values))
        data["Input Voltage Clean"] = PostProcessor().post_process_voltage(data, "Input Voltage", external_change_indexes=change_indexes)
        data["Output Voltage Clean"] = PostProcessor().post_process_voltage(data, "Output Voltage", external_change_indexes=change_indexes)
        # plt.plot(data["Current"])
        # plt.plot(data["Current Clean"])
        # plt.plot(data["Input Voltage Clean"])

        best_error = math.inf
        best_loop_data = None

        for chunk_index in range(0, len(change_indexes) - 2, 1):
            loop_data = data.loc[change_indexes[chunk_index]: change_indexes[chunk_index + 2]]
            # plt.plot(loop_data["Current Clean"])
            initial_value = loop_data["Current Clean"].iloc[0]
            final_value = loop_data["Current Clean"].iloc[-1]
            max_value = loop_data["Current Clean"].max()
            min_value = loop_data["Current Clean"].min()
            error = abs(float(final_value - initial_value)) / (max_value - min_value)
            if error < best_error:
                best_error = error
                best_loop_data = loop_data

        # plt.show()

        return best_error, best_loop_data

    def calculate_new_voltage_proportion(self, loop_data, desired_dc_current, current_voltage_proportion=None):
        # current_peak_to_peak = loop_data["Current Clean"].max() - loop_data["Current Clean"].min()
        voltage_peak_to_peak = loop_data["Input Voltage Clean"].max() - loop_data["Input Voltage Clean"].min()
        # time_period = (loop_data["time"].max() - loop_data["time"].min()) / 2
        dc_current = loop_data["Current Clean"].mean()
        voltage_unbalance = abs(loop_data["Input Voltage Clean"].max()) - abs(loop_data["Input Voltage Clean"].min())

        current_impedance = voltage_unbalance / dc_current
        new_voltage_unbalance = desired_dc_current * current_impedance
        new_voltage_proportion = (new_voltage_unbalance + voltage_peak_to_peak) / (2 * voltage_peak_to_peak)
        # inductance = voltage_peak_to_peak / current_peak_to_peak * time_period

        if current_voltage_proportion is not None:
            calculated_voltage_proportion = (voltage_unbalance + voltage_peak_to_peak) / (2 * voltage_peak_to_peak)
            ratio = current_voltage_proportion / calculated_voltage_proportion
            new_voltage_proportion *= ratio

        return new_voltage_proportion


if __name__ == "__main__":

    if len(sys.argv) == 1:
        print("Missing argument: CSV filename")
        sys.exit()
    
    data = pandas.read_csv(sys.argv[1])
    # plt.plot(data["Current"])
    # change_indexes, change_values = PostProcessor().get_current_change_indexes(data, "Current")
    # data["Input Voltage Clean"] = PostProcessor().post_process_voltage(data, "Input Voltage", external_change_indexes=change_indexes)
    # data["Output Voltage Clean"] = PostProcessor().post_process_voltage(data, "Output Voltage", external_change_indexes=change_indexes)
    # data["Current Clean"] = PostProcessor().post_process_current(data, "Current", external_change_indexes_and_values=(change_indexes, change_values))

    plt.plot(data["Input Voltage"])
    plt.plot(data["Output Voltage"])
    plt.plot(data["Current"])
    plt.show()
    # plt.plot(data["Input Voltage Clean"])
    # plt.plot(data["Output Voltage Clean"])
    # plt.plot(data["Current Clean"])
    # # plt.plot(data["Output Voltage Clean"])
    # # # plt.plot(data["diff"])
    # plt.show()

    error, best_loop = PostProcessor().analyze_loops(data)
    print(f"error: {error}")
    print(f"best_loop: {best_loop}")
    new_voltage_proportion = PostProcessor().calculate_new_voltage_proportion(best_loop, 4, 0.67)
    print(f"new_voltage_proportion: {new_voltage_proportion}")
    # print(f"best_loop_inductance: {best_loop_inductance}")
    # print(f"best_loop_average: {best_loop_average}")
