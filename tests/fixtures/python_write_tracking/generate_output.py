import os
import matplotlib.pyplot as plt

output_path = r"C:\project\output"

for case in ["A", "B"]:
    case_folder = os.path.join(output_path, case)
    filename = f"{case}_result.pdf"
    filepath = os.path.join(case_folder, filename)
    fig, ax = plt.subplots()
    fig.savefig(filepath, format='pdf')
