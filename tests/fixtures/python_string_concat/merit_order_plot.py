import matplotlib.pyplot as plt

output_path = r"C:\project\output"
save_path = output_path + r"\merit_order.png"
fig, ax = plt.subplots()
fig.savefig(save_path, dpi=300, bbox_inches="tight")
