from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR

from co_lib import Co_Lib as CL
from xgen_tools import *
COCOPIE_MAP = {'epochs' : 'common_train_epochs'}


class Net(nn.Module):

    def __init__(self, scaling_down_factor):
        super(Net, self).__init__()

        _convs = 3
        _cov1kernels_org = 128
        _cov2kernels_org = 2*_cov1kernels_org
        _cov3kernels_org = 2*_cov1kernels_org
        _inputsize = 28
        _classes = 10
        _batchsize = 128
        _kernelsize = 3
        _dropoutp = 0.5
        _poolsize = 2

        print("scaling_down_factor:", scaling_down_factor)
        cov1kernels = max(1,int(_cov1kernels_org * (1-scaling_down_factor/2))) # prune less at the beginning
        print("Cov1: ", 1, " ", cov1kernels, " ", _kernelsize, " ", 1)
        self.conv1 = nn.Conv2d(1, cov1kernels, _kernelsize, 1)

        cov2kernels = max(1,int(_cov2kernels_org * (1-scaling_down_factor)))
        print("Cov2: ", cov1kernels, " ", cov2kernels, " ", _kernelsize, " ", 1)
        self.conv2 = nn.Conv2d(cov1kernels, cov2kernels, _kernelsize, 1)

        cov3kernels = max(1,int(_cov3kernels_org * (1-scaling_down_factor))) # prune less at the end
        print("Cov3: ", cov2kernels, " ", cov3kernels, " ", _kernelsize, " ", 1)
        self.conv3 = nn.Conv2d(cov2kernels, cov3kernels, _kernelsize, 1)
        self.dropout1 = nn.Dropout(_dropoutp)

        fcwidth = max(1, cov3kernels*int((_inputsize-2*_convs)/_poolsize)*int((_inputsize-2*_convs)/_poolsize))
        print("Fc:  ", fcwidth, " ", _classes, " ", 1) # each conv reduces the size by 2 at the boundary
        self.fc = nn.Linear(fcwidth, _classes)

    def forward(self, x):
        x = self.conv1(x)
        x = F.relu(x)
        x = self.conv2(x)
        x = F.relu(x)
        x = self.conv3(x)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)
        x = self.dropout1(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)
        output = F.log_softmax(x, dim=1)
        return output


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss = CL.update_loss(loss)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.item()))
            if args.dry_run:
                break


def test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction='sum').item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    test_accuracy = 100. * correct / len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        test_accuracy))
    return test_accuracy

def training_main(args_ai):
    # Training settings
    parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
    parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=9, metavar='N',
                        help='number of epochs to train (default: 14)')
    parser.add_argument('--lr', type=float, default=1.0, metavar='LR',
                        help='learning rate (default: 1.0)')
    parser.add_argument('--gamma', type=float, default=0.7, metavar='M',
                        help='Learning rate step gamma (default: 0.7)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='quickly check a single pass')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--save-model', action='store_true', default=False,
                        help='For Saving the current Model')
    args = parser.parse_args()
    orginalArgs, args_ai = xgen_init(args, map = COCOPIE_MAP)

    scaling_factor = args_ai['origin']['scaling_factor']

    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)

    device = torch.device("cuda" if use_cuda else "cpu")

    train_kwargs = {'batch_size': args.batch_size}
    test_kwargs = {'batch_size': args.test_batch_size}
    if use_cuda:
        cuda_kwargs = {'num_workers': 1,
                       'pin_memory': True,
                       'shuffle': True}
        train_kwargs.update(cuda_kwargs)
        test_kwargs.update(cuda_kwargs)

    transform=transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
        ])
    dataset1 = datasets.MNIST('/xgen/data/classification-digitnet', train=True,
                       transform=transform)
    dataset2 = datasets.MNIST('/xgen/data/classification-digitnet', train=False,
                       transform=transform)
    train_loader = torch.utils.data.DataLoader(dataset1,**train_kwargs)
    test_loader = torch.utils.data.DataLoader(dataset2, **test_kwargs)

    model = Net(scaling_factor).to(device)
    xgen_load(model,args_ai=args_ai)
    optimizer = optim.Adadelta(model.parameters(), lr=args.lr)

    scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)
    CL.init(args=args_ai, model= model, optimizer=optimizer, data_loader=train_loader)

    for epoch in range(1, args.epochs + 1):
        CL.before_each_train_epoch(epoch=epoch)
        train(args, model, device, train_loader, optimizer, epoch)
        evaluationResult = test(model, device, test_loader)
        xgen_record(args_ai,model,evaluationResult,epoch=epoch)
        scheduler.step()
        CL.after_scheduler_step(epoch=epoch)
    xgen_record(args_ai, model, -1, -1)
    if args.save_model:
        torch.save(model.state_dict(), "mnist_cnn.pt")
    return args_ai


if __name__ == '__main__':
    args_ai =None
    training_main(args_ai)
