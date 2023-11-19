import json
import os

with open("accounts/binary/accounts.json", "r") as f:
    accounts = json.load(f)

uin_list = []
for i in accounts["accounts"]:
    uin = i["uin"]
    uin_list.append(uin)

if not uin_list:
    print("No accounts")
    exit()

print(uin_list)

for file in os.listdir("accounts"):
    if not os.path.isdir("accounts/" + file):
        continue

    if not file.isdigit():
        continue

    if int(file) in uin_list:
        continue

    print("Remove " + file)
    os.system("rm -rf accounts/" + file)
