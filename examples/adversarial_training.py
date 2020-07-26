import OpenAttack
import torch

def make_model(vocab_size):
    """
    see `tutorial - pytorch <https://pytorch.org/tutorials/beginner/text_sentiment_ngrams_tutorial.html#define-the-model>`__
    """
    import torch.nn as nn
    class TextSentiment(nn.Module):
        def __init__(self, vocab_size, embed_dim=32, num_class=2):
            super().__init__()
            self.embedding = nn.EmbeddingBag(vocab_size, embed_dim)
            self.fc = nn.Linear(embed_dim, num_class)
            self.softmax = nn.Softmax(dim=1)
            self.init_weights()

        def init_weights(self):
            initrange = 0.5
            self.embedding.weight.data.uniform_(-initrange, initrange)
            self.fc.weight.data.uniform_(-initrange, initrange)
            self.fc.bias.data.zero_()

        def forward(self, text):
            embedded = self.embedding(text, None)
            return self.softmax(self.fc(embedded))
    return TextSentiment(vocab_size)

def prepare_data():
    vocab = {
        "<UNK>": 0,
        "<PAD>": 1
    }
    train, valid, test = OpenAttack.loadDataset("SST")
    tp = OpenAttack.text_processors.DefaultTextProcessor()
    for dataset in [train, valid, test]:
        for inst in dataset:
            inst.tokens = list(map(lambda x:x[0], tp.get_tokens(inst.x)))
            for token in inst.tokens:
                if token not in vocab:
                    vocab[token] = len(vocab)
    return train, valid, test, vocab

def make_batch(data, vocab):
    batch_x = [
        [ 
            vocab[token] if token in vocab else vocab["<UNK>"]
                for token in inst.tokens
        ] for inst in data
    ]
    max_len = max( [len(inst.tokens) for inst in data] )
    batch_x = [
        sentence + [vocab["<PAD>"]] * (max_len - len(sentence))
            for sentence in batch_x
    ]
    batch_y = [
        inst.y for inst in data
    ]
    return torch.LongTensor(batch_x), torch.LongTensor(batch_y)


def train_epoch(model, dataset, vocab, batch_size=128, learning_rate=5e-3):
    dataset = dataset.shuffle().reset_index()
    model.train()
    criterion = torch.nn.NLLLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    avg_loss = 0

    for start in range(0, len(dataset), batch_size):
        train_x, train_y = make_batch(dataset[start: start + batch_size], vocab)
        pred = model(train_x)
        loss = criterion(pred.log(), train_y)

        optimizer.zero_grad()

        loss.backward()

        optimizer.step()
        
        avg_loss += loss.item()
    return avg_loss / len(dataset)

def train_model(model, data_train, data_valid, vocab, num_epoch=10, verbose=True):
    mx_acc = None
    mx_model = None
    for i in range(num_epoch):
        loss = train_epoch(model, data_train, vocab)
        clsf = OpenAttack.PytorchClassifier(model, word2id=vocab)
        accuracy = len(data_valid.eval(clsf).correct()) / len(data_valid)
        if verbose:
            print("Epoch %d: loss: %lf, accuracy %lf" % (i, loss, accuracy))
        if mx_acc is None or mx_acc < accuracy:
            mx_model = model.state_dict()
    model.load_state_dict(mx_model)
    return model

def attack(classifier, dataset, attacker = OpenAttack.attackers.PWWSAttacker(), verbose=True):
    attack_eval = OpenAttack.attack_evals.DefaultAttackEval(
        attacker = attacker,
        classifier = classifier,
        success_rate = True
    )
    correct_samples = dataset.eval(classifier).correct()

    accuracy = len(correct_samples) / len(dataset)

    adversarial_samples = attack_eval.generate_adv(correct_samples)
    attack_success_rate = attack_eval.get_result()["Attack Success Rate"]

    if verbose:
        print("Accuracy: %lf%%\nAttack success rate: %lf%%" % (accuracy * 100, attack_success_rate * 100))

    tp = OpenAttack.text_processors.DefaultTextProcessor()
    for inst in adversarial_samples:
        inst.tokens = list(map(lambda x:x[0], tp.get_tokens(inst.x)))

    return adversarial_samples

def main():
    print("Loading data")
    train, valid, test, vocab = prepare_data()
    model = make_model(len(vocab))

    print("Training")
    trained_model = train_model(model, train, valid, vocab)
    
    print("Generating adversarial samples (this step will take dozens of minutes)")
    clsf = OpenAttack.PytorchClassifier(trained_model, word2id=vocab)
    adversarial_samples = attack(clsf, train)

    print("Tuning classifier")
    finetune_model = train_model(trained_model, train + adversarial_samples, valid, vocab)

    print("Testing enhanced model (this step will take dozens of minutes)")
    attack(clsf, train)

    


if __name__ == '__main__':
    main()