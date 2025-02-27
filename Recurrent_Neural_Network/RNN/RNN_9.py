import matplotlib.pyplot as plt
import pandas as pd
import datetime
import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import Dataset, DataLoader
import copy
import torchvision
import torchvision.transforms as transforms
# % matplotlib inline

n = 30  # 前n天的数据
n_m = 10  # 预测未来n_m天的数据
LR = 0.001
EPOCH = 100
batch_size = 20
train_end = -500
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# 通过一个序列来生成一个31*(count(*)-train_end)矩阵（用于处理时序的数据）
# 其中最后一列维标签数据。就是把当天的前n天作为参数，当天的数据作为label
def generate_data_by_n_days(series, n, index=False):
    if len(series) <= n:
        raise Exception("The Length of series is %d, while affect by (n=%d)." % (len(series), n))
    df = pd.DataFrame()
    for i in range(n):
        df['c%d' % i] = series.tolist()[i:-(n - i)]
    df['y'] = series.tolist()[n:]

    if index:
        df.index = series.index[n:]
    return df

# 参数n与上相同。train_end表示的是后面多少个数据作为测试集。
def readData(column='high', n=30, all_too=True, index=False, train_end=-500):
    df = pd.read_csv("sh300.csv", index_col=0)
    date_index = list(range(df.shape[0]))
    date_index.reverse()
    df['date_index'] = date_index
    df.sort_values(by='date_index', inplace=True, ascending=True)
    # 以日期为索引
    df.index = list(map(lambda x: datetime.datetime.strptime(x, "%Y-%m-%d"), df.index))
    # 获取每天的最高价
    df_column = df[column].copy()
    # 拆分为训练集和测试集
    df_column_train, df_column_test = df_column[:train_end], df_column[train_end - n:]  # [-2998:-1]
    # 生成训练数据
    df_generate_train = generate_data_by_n_days(df_column_train, n, index=index)
    if all_too:
        return df_generate_train, df_column, df.index.tolist()
    return df_generate_train

# 定义模型
class RNN(nn.Module):
    def __init__(self, input_size):
        super(RNN, self).__init__()
        self.rnn = nn.LSTM(input_size=input_size, hidden_size=64, num_layers=1, batch_first=True)
        self.out = nn.Sequential(nn.Linear(64, 1))

    def forward(self, x):
        r_out, (h_n, h_c) = self.rnn(x, None)  # None即隐层状态用0初始化
        out = self.out(r_out)
        return out

class mytrainset(Dataset):
    def __init__(self, data):
        self.data, self.label = data[:, :-1].float(), data[:, -1].float()

    def __getitem__(self, index):
        return self.data[index], self.label[index]

    def __len__(self):
        return len(self.data)

# 训练模型
from pandas.plotting import register_matplotlib_converters
register_matplotlib_converters()
# 获取训练数据、原始数据、索引等信息
df, df_all, df_index = readData('high', n=n, train_end=train_end)
# 可视化原高价数据
df_all = np.array(df_all.tolist())
plt.plot(df_index, df_all, label='real-data')
plt.legend(loc='upper right')
# plt.show()

# 对数据进行预处理，规范化及转换为Tensor
df_numpy = np.array(df)
df_numpy_mean = np.mean(df_numpy)
df_numpy_std = np.std(df_numpy)
df_numpy = (df_numpy - df_numpy_mean) / df_numpy_std
df_tensor = torch.Tensor(df_numpy)
trainset = mytrainset(df_tensor)
trainloader = DataLoader(trainset, batch_size=batch_size, shuffle=False)

# 记录损失值在web上展示
from visdom import Visdom

rnn = RNN(n).to(device)  # 模型实例化
optimizer = torch.optim.Adam(rnn.parameters(), lr=LR)
loss_func = nn.MSELoss()

for step in range(EPOCH):
    for tx, ty in trainloader:
        tx = tx.to(device)
        ty = ty.to(device)

        # 在第1个维度上添加一个维度为1的维度，形状变为[batch,seq_len,input_size]
        output = rnn(torch.unsqueeze(tx, dim=1)).to(device)
        loss = loss_func(torch.squeeze(output), ty)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    print("周期：", step)


generate_data_train = []
generate_data_test = []
test_index = len(df_all) + train_end
df_all_normal = (df_all - df_numpy_mean) / df_numpy_std
df_all_normal_tensor = torch.Tensor(df_all_normal)  # 测试用的数据

for i in range(n, len(df_all)):
    x = df_all_normal_tensor[i - n:i].to(device)
    # rnn的输入必须是3维，故需添加两个1维的维度，最后成为[1,1,input_size]
    x = torch.unsqueeze(torch.unsqueeze(x, dim=0), dim=0)
    y = rnn(x).to(device)
    # 更新测试数据
    if i < test_index:
        generate_data_train.append(torch.squeeze(y).detach().cpu().numpy() * df_numpy_std + df_numpy_mean)
    else:
        generate_data_test.append(torch.squeeze(y).detach().cpu().numpy() * df_numpy_std + df_numpy_mean)

plt.plot(df_index[n:train_end], generate_data_train, label='generate_train')
plt.plot(df_index[train_end:], generate_data_test, label='generate_test')
plt.plot(df_index[train_end:], df_all[train_end:], label='real-data')
plt.legend()
plt.show()

plt.clf()
plt.plot(df_index[train_end:], df_all[train_end:], label='real-data')
plt.plot(df_index[train_end:], generate_data_test[train_end:], label='generate_test')
plt.legend()
plt.show()