import torch
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
from network import PINN
import torch
import torch.functional as F
from real_sol import real_sol

# pour utiliser le gpu au lieu de cpu
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(device)

with_rnn = False
net = PINN(with_rnn=with_rnn)
net._model_summary()

########################################################### POINTS DEFINITION ###########################################################
#########################################################################################################################################
N_i, N_b, N_r = 200, 200, 200

t_i = torch.zeros(N_i, 1)
# le view c'est pr avoir le format torch
x_i = torch.linspace(0, 1, N_i).view(N_i, 1)
#u_0 = torch.sin(np.pi*x_0)
u_i = t_i + 1*(torch.sin(np.pi*x_i) + 0.5*torch.sin(4*np.pi*x_i))

t_b = torch.linspace(0, 1, N_b).view(N_b, 1)
# x_b evenly distributed in 0 or 1 with total N_b points
# Pour fair en sorte que la CI soit soit en haut soit en bas
x_b = torch.bernoulli(0.5*torch.ones(N_b, 1))
u_b = torch.zeros(N_b, 1)

# On génère des pts randoms dans le domaine sur lesquels on va calculer le residu
t_r = torch.rand(N_r, 1)
x_r = torch.rand(N_r, 1)


############################################################## POINTS PLOTTING #############################################################
############################################################################################################################################
def plot_training_points(t_0, t_b, t_r, x_0, x_b, x_r, u_0, u_b):
    """
    Input: -dimension = spatial dimension
           -time_x = [t_0,t_b,t_r,x_0,x_b,x_r,u_0,u_b]
    Output: display training points in either 1,2 or 3D
    """
    fig = plt.figure(figsize=(9, 6))
    ax = fig.add_subplot(111)
    ax.scatter(t_0, x_0[:, 0], c=u_0, marker='X', vmin=-1, vmax=1)
    ax.scatter(t_b, x_b[:, 0], c=u_b, marker='X', vmin=-1, vmax=1)
    ax.scatter(t_r, x_r[:, 0], c='r', marker='.', alpha=0.1)
    ax.set_xlabel('$t$')
    ax.set_ylabel('$x1$')
    ax.set_title('Positions of collocation points and boundary data')
    plt.show()


plot_training_points(t_i.data.numpy(),
                     t_b.data.numpy(),
                     t_r.data.numpy(),
                     x_i.data.numpy(),
                     x_b.data.numpy(),
                     x_r.data.numpy(),
                     u_i.data.numpy(),
                     u_b.data.numpy())

############################################################## SEQUENCES FOR RNN ###################################################################
####################################################################################################################################################


def data_to_rnn_sequences(data, seq_len):
    """Converts data to sequences of length seq_len"""
    sequences = []
    for i in range(len(data)-seq_len):
        sequences.append(data[i:i+seq_len])
    return torch.stack(sequences)


def all_data_to_sequences(x_r, t_r,
                          u_b, x_b, t_b,
                          u_i, x_i, t_i, seq_len):
    x_r, t_r = data_to_rnn_sequences(
        x_r, seq_len), data_to_rnn_sequences(t_r, seq_len)
    u_b, x_b, t_b = data_to_rnn_sequences(u_b, seq_len), data_to_rnn_sequences(
        x_b, seq_len), data_to_rnn_sequences(t_b, seq_len)
    u_i, x_i, t_i = data_to_rnn_sequences(u_i, seq_len), data_to_rnn_sequences(
        x_i, seq_len), data_to_rnn_sequences(t_i, seq_len)
    return x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i


def sequence_to_label(sequence):
    """Converts a sequence to a label"""
    return sequence[:, -1, :]


def all_data_to_label(x_r, t_r,
                      u_b, x_b, t_b,
                      u_i, x_i, t_i):
    x_r, t_r = sequence_to_label(x_r), sequence_to_label(t_r)
    u_b, x_b, t_b = sequence_to_label(
        u_b), sequence_to_label(x_b), sequence_to_label(t_b)
    u_i, x_i, t_i = sequence_to_label(
        u_i), sequence_to_label(x_i), sequence_to_label(t_i)
    x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i = x_r.to(device), t_r.to(device), u_b.to(
        device), x_b.to(device), t_b.to(device), u_i.to(device), x_i.to(device), t_i.to(device)
    return x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i


if with_rnn:
    x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i = all_data_to_sequences(x_r, t_r,
                                                                   u_b, x_b, t_b,
                                                                   u_i, x_i, t_i, seq_len=10)
    # x_r_label,t_r_label,u_b_label,x_b_label,t_b_label,u_i_label,x_i_label,t_i_label = all_data_to_label(x_r,t_r,
    #        u_b,x_b,t_b,
    #        u_i,x_i,t_i)

############################################################## TRAIN VAL SPLIT ###################################################################


def val_split(x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i, split=0.2):
    """Splits data into training and validation set with random order"""
    x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i = x_r.to(device), t_r.to(device), u_b.to(
        device), x_b.to(device), t_b.to(device), u_i.to(device), x_i.to(device), t_i.to(device)
    N_r = x_r.shape[0]
    N_b = x_b.shape[0]
    N_i = x_i.shape[0]
    N_r_val = int(N_r*split)
    N_b_val = int(N_b*split)
    N_i_val = int(N_i*split)
    N_r_train = N_r - N_r_val
    N_b_train = N_b - N_b_val
    N_i_train = N_i - N_i_val
    # Permet de mélanger pr que les données ne soient pas dans l'ordre pr l'entrainement
    idx_r = torch.randperm(N_r)
    idx_b = torch.randperm(N_b)
    idx_i = torch.randperm(N_i)
    x_r_train, t_r_train = x_r[idx_r[:N_r_train]], t_r[idx_r[:N_r_train]]
    x_r_val, t_r_val = x_r[idx_r[N_r_train:]], t_r[idx_r[N_r_train:]]
    u_b_train, x_b_train, t_b_train = u_b[idx_b[:N_b_train]
                                          ], x_b[idx_b[:N_b_train]], t_b[idx_b[:N_b_train]]
    u_b_val, x_b_val, t_b_val = u_b[idx_b[N_b_train:]
                                    ], x_b[idx_b[N_b_train:]], t_b[idx_b[N_b_train:]]
    u_i_train, x_i_train, t_i_train = u_i[idx_i[:N_i_train]
                                          ], x_i[idx_i[:N_i_train]], t_i[idx_i[:N_i_train]]
    u_i_val, x_i_val, t_i_val = u_i[idx_i[N_i_train:]
                                    ], x_i[idx_i[N_i_train:]], t_i[idx_i[N_i_train:]]
    return [x_r_train, t_r_train, u_b_train, x_b_train, t_b_train, u_i_train, x_i_train, t_i_train], [x_r_val, t_r_val, u_b_val, x_b_val, t_b_val, u_i_val, x_i_val, t_i_val]


def val_split_with_labels(x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i, split=0.2):
    """Splits data into training and validation set with random order"""
    x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i = x_r.to(device), t_r.to(device), u_b.to(
        device), x_b.to(device), t_b.to(device), u_i.to(device), x_i.to(device), t_i.to(device)
    N_r = x_r.shape[0]
    N_b = x_b.shape[0]
    N_i = x_i.shape[0]
    N_r_val = int(N_r*split)
    N_b_val = int(N_b*split)
    N_i_val = int(N_i*split)
    N_r_train = N_r - N_r_val
    N_b_train = N_b - N_b_val
    N_i_train = N_i - N_i_val
    idx_r = torch.randperm(N_r)
    idx_b = torch.randperm(N_b)
    idx_i = torch.randperm(N_i)
    x_r_train, t_r_train = x_r[idx_r[:N_r_train]], t_r[idx_r[:N_r_train]]
    x_r_val, t_r_val = x_r[idx_r[N_r_train:]], t_r[idx_r[N_r_train:]]
    u_b_train, x_b_train, t_b_train = u_b[idx_b[:N_b_train]
                                          ], x_b[idx_b[:N_b_train]], t_b[idx_b[:N_b_train]]
    u_b_val, x_b_val, t_b_val = u_b[idx_b[N_b_train:]
                                    ], x_b[idx_b[N_b_train:]], t_b[idx_b[N_b_train:]]
    u_i_train, x_i_train, t_i_train = u_i[idx_i[:N_i_train]
                                          ], x_i[idx_i[:N_i_train]], t_i[idx_i[:N_i_train]]
    u_i_val, x_i_val, t_i_val = u_i[idx_i[N_i_train:]
                                    ], x_i[idx_i[N_i_train:]], t_i[idx_i[N_i_train:]]
    x_r_train_label, t_r_train_label = sequence_to_label(
        x_r_train), sequence_to_label(t_r_train)
    x_r_val_label, t_r_val_label = sequence_to_label(
        x_r_val), sequence_to_label(t_r_val)
    u_b_train_label, x_b_train_label, t_b_train_label = sequence_to_label(
        u_b_train), sequence_to_label(x_b_train), sequence_to_label(t_b_train)
    u_b_val_label, x_b_val_label, t_b_val_label = sequence_to_label(
        u_b_val), sequence_to_label(x_b_val), sequence_to_label(t_b_val)
    u_i_train_label, x_i_train_label, t_i_train_label = sequence_to_label(
        u_i_train), sequence_to_label(x_i_train), sequence_to_label(t_i_train)
    u_i_val_label, x_i_val_label, t_i_val_label = sequence_to_label(
        u_i_val), sequence_to_label(x_i_val), sequence_to_label(t_i_val)
    return [x_r_train, t_r_train, u_b_train, x_b_train, t_b_train, u_i_train, x_i_train, t_i_train], [x_r_val, t_r_val, u_b_val, x_b_val, t_b_val, u_i_val, x_i_val, t_i_val], [x_r_train_label, t_r_train_label, u_b_train_label, x_b_train_label, t_b_train_label, u_i_train_label, x_i_train_label, t_i_train_label], [x_r_val_label, t_r_val_label, u_b_val_label, x_b_val_label, t_b_val_label, u_i_val_label, x_i_val_label, t_i_val_label]


if not with_rnn:
    train_data, val_data = val_split(
        x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i, split=0.2)
else:
    train_data, val_data, train_data_labels, val_data_labels = val_split_with_labels(
        x_r, t_r, u_b, x_b, t_b, u_i, x_i, t_i, split=0.2)
    train_data = train_data + train_data_labels
    val_data = val_data + val_data_labels

########################################################### PLOTTING FUNCTIONS ###########################################################
##########################################################################################################################################


def plot1dgrid_real(lb, ub, N, model, k, with_rnn=False):
    """Same for the real solution"""
    model = model.net
    x1space = np.linspace(lb[0], ub[0], N)
    tspace = np.linspace(lb[1], ub[1], N)
    T, X1 = np.meshgrid(tspace, x1space)
    T = torch.from_numpy(T).view(1, N*N, 1).to(device).float()
    X1 = torch.from_numpy(X1).view(1, N*N, 1).to(device).float()
    if not with_rnn:
        T = T.transpose(0, 1).squeeze(-1)
        X1 = X1.transpose(0, 1).squeeze(-1)
    else:
        T = T.transpose(0, 1)
        X1 = X1.transpose(0, 1)
    upred = model(X1, T)
    U = torch.squeeze(upred).cpu().detach().numpy()
    U = upred.view(N, N).detach().cpu().numpy()
    T, X1 = T.view(N, N).detach().cpu().numpy(), X1.view(
        N, N).detach().cpu().numpy()
    z_array = np.zeros((N, N))
    for i in range(N):
        z_array[:, i] = U[i]

    plt.style.use('dark_background')

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.scatter(T, X1, c=U, marker='X', vmin=-1, vmax=1)
    ax.set_xlabel('$t$')
    ax.set_ylabel('$x1$')
    plt.savefig(f'results/generated_{k}')
    plt.close()

# Plot train and val losses on same figure


def plot_loss(train_losses, val_losses, accuracy):
    plt.style.use('dark_background')
    plt.plot(train_losses, label='train')
    plt.plot(val_losses, label='val')
    plt.plot(accuracy, label="accuracy")
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    plt.savefig(f'results/loss')
    plt.close()

########################################################### TRAINING ###########################################################
################################################################################################################################


def train(model, train_data, val_data,
          epochs):
    epochs = tqdm(range(epochs), desc="Training")
    losses = []
    val_losses = []
    acc = []
    for epoch in epochs:
        # Shuffle train_data
        # On remélange pr pas entrainer sur la mm chose ds le mm ordre
        index_shuf = torch.randperm(train_data[0].shape[0])
        train_data_new = [train_data[i][index_shuf]
                          for i in range(len(train_data))]
        train_data = train_data_new
        loss = model.train_step(train_data)
        val_loss = model.val_step(val_data)
        accuracy = model.accuracy_step(val_data)
        epochs.set_postfix(loss=loss, epochs=epoch, val_loss=val_loss)
        losses.append(loss)
        val_losses.append(val_loss)
        acc.append(accuracy)
        if epoch % 100 == 0:
            plot1dgrid_real(lb, ub, N, model, epoch)
        if epoch % 1000 == 0:
            torch.save(model.net.state_dict(), f"results/model_{epoch}.pt")
        # Plot_losses
        plot_loss(losses, val_losses, acc)


def train_rnn(model, train_data, val_data, epochs):
    epochs = tqdm(range(epochs), desc="Training")
    losses = []
    val_losses = []
    for epoch in epochs:
        # Shuffle train_data
        index_shuf = torch.randperm(train_data[0].shape[0])
        train_data_new = [train_data[0][index_shuf], train_data[1][index_shuf], train_data[2][index_shuf], train_data[3][index_shuf], train_data[4][index_shuf], train_data[5][index_shuf], train_data[6][index_shuf], train_data[7][index_shuf],
                          train_data[8][index_shuf], train_data[9][index_shuf], train_data[10][index_shuf], train_data[11][index_shuf], train_data[12][index_shuf], train_data[13][index_shuf], train_data[14][index_shuf], train_data[15][index_shuf]]
        train_data = train_data_new
        loss = model.train_step_rnn(train_data)
        val_loss = model.val_step_rnn(val_data)
        epochs.set_postfix(loss=loss, epochs=epoch, val_loss=val_loss)
        losses.append(loss)
        val_losses.append(val_loss)
        if epoch % 100 == 0:
            plot1dgrid_real(lb, ub, N, model, epoch, True)
        if epoch+1 % 1000 == 0:
            model.net.save_weights(f'weights/weights_{epoch}')
        plot_loss(losses, val_losses)


lb = [0, 0]
ub = [1, 1]
N = 70
with torch.backends.cudnn.flags(enabled=False):
    if with_rnn:
        train_rnn(net, train_data, val_data, epochs=1000)
    else:
        train(net, train_data, val_data, epochs=1000)
