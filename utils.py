import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from network import Model
import numpy as np
import config
import glob
import re
import os
FILE_PATH = os.path.dirname(os.path.abspath(__file__))
VEC_PATH = FILE_PATH + '/data/word2vec.txt'


def train(dataset, learning_rate, total_epoch, device, save_epoch=5, log_step=100, test_epoch=1):
    net = model(dataset, device=device)
    model_name = dataset.singer or "pre_trained"
    pre_trained_model = check_pre_trained_model()
    if pre_trained_model:
        pre_trained_state_dict = torch.load(FILE_PATH + config.model_path + pre_trained_model)
        state_dict = net.state_dict()
        state_dict.update(pre_trained_state_dict)
        net.load_state_dict(state_dict)
        if dataset.singer:
            start_epoch = 0
        else:
            start_epoch = int(re.findall("\d+", pre_trained_model)[0])
    else:
        start_epoch = 0

    loss_weight = torch.ones(dataset.target_vocab_size).to(device)
    loss_weight[dataset.stoi["<go>"]] = 0
    loss_weight[dataset.stoi["<unk>"]] = 0
    loss_weight[dataset.stoi["<pad>"]] = 0

    criterion = nn.NLLLoss(reduction='mean', weight=loss_weight)
    optimizer = optim.Adam(net.parameters(), lr=learning_rate)
    net.train()
    for epoch in range(start_epoch, total_epoch):
        total_loss = 0
        if epoch % config.decay_epoch == 0:
            learning_rate = learning_rate * config.decay_rate
            print("current lr:", learning_rate)
            optimizer = optim.Adam(net.parameters(), lr=learning_rate)
        if epoch % save_epoch == 0 and epoch > start_epoch:
            torch.save(state_dict_without_embedding(net), FILE_PATH + config.model_path + model_name + '_%d.pkl' % epoch)
        for step, batch in enumerate(dataset.data_iter):
            encoder_input, encoder_length = batch.encoder
            decoder_input, decoder_length = batch.decoder
            target = batch.target

            logists = net(encoder_input, encoder_length, decoder_input, decoder_length)
            logists = F.log_softmax(logists, dim=2)

            loss = criterion(logists.permute(0, 2, 1), target[:, :logists.shape[1]])
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), config.clip_grad)
            optimizer.step()
            total_loss += loss.cpu().data.numpy()
            if step % log_step == 0:
                if step > 0:
                    print("epoch", epoch, "step", step, "loss:", total_loss / log_step)
                    total_loss = 0
                elif step == 0 and epoch % test_epoch == 0:
                    test(dataset, net, encoder_input, encoder_length, decoder_input, decoder_length, target)


def model(dataset, model_name=None, device=None, train=True):
    net = Model(vocab_size=dataset.vocab_size, embedding_dim=config.embedding_dim,
                output_size=dataset.target_vocab_size,
                encoder_hidden_size=config.encoder_hidden_size, decoder_hidden_size=config.decoder_hidden_size,
                encoder_layers=config.encoder_layers, decoder_layers=config.decoder_layers,
                dropout=config.dropout, embedding_weights=dataset.vector_weights, device=device)
    if model_name:
        pre_trained_state_dict = torch.load(FILE_PATH + config.model_path + model_name)
        state_dict = net.state_dict()
        state_dict.update(pre_trained_state_dict)
        net.load_state_dict(state_dict)
    net.train() if train else net.eval()
    return net


def state_dict_without_embedding(net):
    state_dict = net.state_dict()
    for s in state_dict.copy().keys():
        if "embedding" in s:
            state_dict.pop(s)
    return state_dict


def check_pre_trained_model():
    if not os.path.exists(FILE_PATH + config.model_path):
        os.mkdir(FILE_PATH + config.model_path)
        print("path '%s' doesn't exist, create it." % config.model_path)
    file_names = glob.glob(FILE_PATH + config.model_path + "pre_trained_*.pkl")
    if len(file_names) == 0:
        print("there isn't any pre-trained model in path '%s'" % (FILE_PATH + config.model_path))
        return None
    else:
        model_epoch = sorted([int(re.findall("\d+", n)[0]) for n in file_names])
        max_epoch = max(model_epoch)
        print("the latest pre-trained model is pre_trained_%d.pkl" % max_epoch)
        return "pre_trained_%d.pkl" % max_epoch


def test(dataset, net, encoder_input, encoder_length, decoder_input, decoder_length, target):
    sample = np.random.randint(encoder_input.shape[0])
    encoder_input = encoder_input[sample: sample + 1]
    encoder_length = encoder_length[sample: sample + 1]
    decoder_input = decoder_input[sample: sample + 1]
    decoder_length = decoder_length[sample: sample + 1]
    target = target[sample: sample + 1]
    input_text = [dataset.itos[i] for i in encoder_input[0][:encoder_length[0]]]
    input_target = [dataset.itos[i] for i in decoder_input[0][:decoder_length[0]]]
    net.eval()
    prediction = net(encoder_input, encoder_length, decoder_input, decoder_length)
    net.train()
    target = [dataset.itos[i] for i in target[0][:decoder_length[0]-1]]
    prediction = [dataset.itos[i] for i in prediction.argmax(2)[0][:decoder_length[0]-1]]
    print("encoder输入:", input_text)
    print("decoder输入:", input_target)
    print("target目标:", target)
    print("预测结果:", prediction)
    print("attention:\n", net.attn.attention[0, :, :, 0])
