import matplotlib.pyplot as plt

case = "base"
ialpha = 1
inu = 2
metric = "welfare"

filename = f"{case}_alpha{ialpha}_nu{inu}_{metric}.pdf"
filepath = f"results/{filename}"
fig, ax = plt.subplots()
fig.savefig(filepath, format='pdf', bbox_inches='tight')
