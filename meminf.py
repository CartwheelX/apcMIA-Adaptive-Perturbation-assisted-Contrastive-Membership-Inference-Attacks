import os
import glob
import torch
import pickle
import numpy as np
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
from sklearn.preprocessing import MinMaxScaler
from torch.nn.functional import normalize
import base64
from torchmetrics.classification import BinaryConfusionMatrix
import pandas as pd
import matplotlib.pyplot as plt
import time
import csv
from sklearn.manifold import TSNE
import seaborn as sns
np.set_printoptions(threshold=np.inf)
from target_shadow_nn_models import *
from opacus import PrivacyEngine
from torch.optim import lr_scheduler
from sklearn.metrics import f1_score, roc_auc_score, roc_curve, auc
# import EarlyStopping
from early_stopping_pytorch import EarlyStopping

def TicTocGenerator():
    # Generator that returns time differences
    ti = 0           # initial time
    tf = time.time() # final time
    while True:
        ti = tf
        tf = time.time()
        yield tf - ti  # returns the time difference

TicToc = TicTocGenerator() # create an instance of the TicTocGen generator

def toc(tempBool=True):
    # Prints the time difference yielded by generator instance TicToc
    tempTimeInterval = next(TicToc)
    # if tempBool:
        # print("Elapsed time: %f seconds." % tempTimeInterval)
    return tempTimeInterval

def tic():
    # Records a time in TicToc, marks the beginning of a time interval
    toc(False)  # The first call to toc() after this will measure from here

def weights_init(m):
    if isinstance(m, nn.Conv2d):
        nn.init.normal_(m.weight.data)
        m.bias.data.fill_(0)
    elif isinstance(m,nn.Linear):
        nn.init.xavier_normal_(m.weight)
        nn.init.constant_(m.bias, 0)
    
class target_train_class():
    def __init__(self, trainloader, testloader, dataset_name, model, device, use_DP, noise, norm, delta, arch):
        self.use_DP = use_DP
        self.device = device
        self.delta = delta
        self.net = model.to(self.device)
        self.trainloader = trainloader
        self.testloader = testloader
        self.arch = arch

        if self.device == 'cuda':
            self.net = torch.nn.DataParallel(self.net)
            cudnn.benchmark = True

        self.criterion = nn.CrossEntropyLoss()
        # self.optimizer = optim.SGD(self.net.parameters(), lr=1e-2, momentum=0.9, weight_decay=5e-4)
        self.noise_multiplier, self.max_grad_norm = noise, norm

        
        if dataset_name == 'purchase':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.MultiStepLR(self.optimizer, [50, 75], 0.1)
        elif dataset_name == 'texas':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.01, momentum=0.9,  weight_decay=1e-4)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.StepLR(self.optimizer, step_size=30, gamma=0.1)
        elif dataset_name == 'adult':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.001, momentum=0.9,  weight_decay=1e-4)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.StepLR(self.optimizer, step_size=30, gamma=0.1)

        else:

            if self.arch == 'vgg16':
                self.optimizer = torch.optim.SGD(model.parameters(), lr=0.005, weight_decay = 0.005, momentum = 0.9)
            elif self.arch == 'wrn':
                # optim.SGD(net.parameters(), lr=cf.learning_rate(args.lr, epoch), momentum=0.9, weight_decay=5e-4)
                self.optimizer = torch.optim.SGD(model.parameters(), lr=0.1, weight_decay=5e-4, momentum = 0.9)
            else:
                self.optimizer = optim.SGD(self.net.parameters(), lr=1e-2,  weight_decay=5e-4, momentum=0.9)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.MultiStepLR(self.optimizer, [50, 75], 0.1)

      
    # Training
    def train(self):
        self.net.train()
        
        train_loss = 0
        correct = 0
        total = 0
        
        for batch_idx, (inputs, targets) in enumerate(self.trainloader):
            if isinstance(targets, list):
                targets = targets[0]

            if str(self.criterion) != "CrossEntropyLoss()":
                targets = torch.from_numpy(np.eye(self.num_classes)[targets]).float()
             
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            self.optimizer.zero_grad()
            # print(f"inputs size: {inputs.size()}, targets size: {targets.size()}")
            # exit()
            outputs = self.net(inputs)

            loss = self.criterion(outputs, targets)
            loss.backward()
            # self.scheduler.step()
            self.optimizer.step()

            train_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            if str(self.criterion) != "CrossEntropyLoss()":
                _, targets= targets.max(1)

            correct += predicted.eq(targets).sum().item()

        if self.use_DP:
            epsilon = self.privacy_engine.accountant.get_epsilon(delta=self.delta)
            # epsilon, best_alpha = self.optimizer.privacy_engine.get_privacy_spent(1e-5)
            print("\u03B5: %.3f \u03B4: 1e-5" % (epsilon))
                
        self.scheduler.step()

        print( 'Train Acc: %.3f%% (%d/%d) | Loss: %.3f' % (100.*correct/total, correct, total, 1.*train_loss/batch_idx))

        return 1.*correct/total


    def saveModel(self, path):
        torch.save(self.net.state_dict(), path)
        

    def get_noise_norm(self):
        return self.noise_multiplier, self.max_grad_norm

    def test(self):
        self.net.eval()
        test_loss = 0
        correct = 0
        total = 0
        with torch.no_grad():
            for inputs, targets in self.testloader:
                if isinstance(targets, list):
                    targets = targets[0]
                if str(self.criterion) != "CrossEntropyLoss()":
                    targets = torch.from_numpy(np.eye(self.num_classes)[targets]).float()

                inputs, targets = inputs.to(self.device), targets.to(self.device)
                outputs = self.net(inputs)

                loss = self.criterion(outputs, targets)

                test_loss += loss.item()
                _, predicted = outputs.max(1)
                total += targets.size(0)
                if str(self.criterion) != "CrossEntropyLoss()":
                    _, targets= targets.max(1)

                correct += predicted.eq(targets).sum().item()

            print( 'Test Acc: %.3f%% (%d/%d)' % (100.*correct/total, correct, total))

        return 1.*correct/total


class shadow_train_class():
    def __init__(self, trainloader, testloader, dataset_name, model, device, use_DP, noise, norm, delta, arch):
        self.use_DP = use_DP
        self.device = device
        self.delta = delta
        self.net = model.to(self.device)
        self.trainloader = trainloader
        self.testloader = testloader
        self.arch = arch

        if self.device == 'cuda':
            self.net = torch.nn.DataParallel(self.net)
            cudnn.benchmark = True

        self.criterion = nn.CrossEntropyLoss()
       
        self.noise_multiplier, self.max_grad_norm = noise, norm

        
        if dataset_name == 'purchase':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.MultiStepLR(self.optimizer, [50, 75], 0.1)
        elif dataset_name == 'texas':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.01, momentum=0.9,  weight_decay=1e-4)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.StepLR(self.optimizer, step_size=30, gamma=0.1)
        elif dataset_name == 'adult':
            self.optimizer = optim.SGD(self.net.parameters(), lr=0.001, momentum=0.9,  weight_decay=1e-4)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.StepLR(self.optimizer, step_size=30, gamma=0.1)

        else:

            if self.arch == 'vgg16':
                self.optimizer = torch.optim.SGD(model.parameters(), lr=0.005, weight_decay = 0.005, momentum = 0.9)
            elif self.arch == 'wrn':
                # optim.SGD(net.parameters(), lr=cf.learning_rate(args.lr, epoch), momentum=0.9, weight_decay=5e-4)
                self.optimizer = torch.optim.SGD(model.parameters(), lr=0.1, weight_decay=5e-4, momentum = 0.9)
            else:
                self.optimizer = optim.SGD(self.net.parameters(), lr=1e-2,  weight_decay=5e-4, momentum=0.9)

            if self.use_DP:
                self.privacy_engine = PrivacyEngine()
                self.model, self.optimizer, self.trainloader = self.privacy_engine.make_private(
                    module=model,
                    optimizer=self.optimizer,
                    data_loader=self.trainloader,
                    noise_multiplier=self.noise_multiplier,
                    max_grad_norm=self.max_grad_norm,
                )          
                print( 'noise_multiplier: %.3f | max_grad_norm: %.3f' % (self.noise_multiplier, self.max_grad_norm))

            self.scheduler = lr_scheduler.MultiStepLR(self.optimizer, [50, 75], 0.1)

      
    # Training
    def train(self):
        self.net.train()
        
        train_loss = 0
        correct = 0
        total = 0
        
        for batch_idx, (inputs, targets) in enumerate(self.trainloader):
            if isinstance(targets, list):
                targets = targets[0]

            if str(self.criterion) != "CrossEntropyLoss()":
                targets = torch.from_numpy(np.eye(self.num_classes)[targets]).float()
             
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            self.optimizer.zero_grad()
            # print(f"inputs size: {inputs.size()}, targets size: {targets.size()}")
            # exit()
            outputs = self.net(inputs)

            loss = self.criterion(outputs, targets)
            loss.backward()
            # self.scheduler.step()
            self.optimizer.step()

            train_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            if str(self.criterion) != "CrossEntropyLoss()":
                _, targets= targets.max(1)

            correct += predicted.eq(targets).sum().item()

        if self.use_DP:
            epsilon = self.privacy_engine.accountant.get_epsilon(delta=self.delta)
            # epsilon, best_alpha = self.optimizer.privacy_engine.get_privacy_spent(1e-5)
            print("\u03B5: %.3f \u03B4: 1e-5" % (epsilon))
                
        self.scheduler.step()

        print( 'Train Acc: %.3f%% (%d/%d) | Loss: %.3f' % (100.*correct/total, correct, total, 1.*train_loss/batch_idx))

        return 1.*correct/total


    def saveModel(self, path):
        torch.save(self.net.state_dict(), path)
        

    def get_noise_norm(self):
        return self.noise_multiplier, self.max_grad_norm

    def test(self):
        self.net.eval()
        test_loss = 0
        correct = 0
        total = 0
        with torch.no_grad():
            for inputs, targets in self.testloader:
                if isinstance(targets, list):
                    targets = targets[0]
                if str(self.criterion) != "CrossEntropyLoss()":
                    targets = torch.from_numpy(np.eye(self.num_classes)[targets]).float()

                inputs, targets = inputs.to(self.device), targets.to(self.device)
                outputs = self.net(inputs)

                loss = self.criterion(outputs, targets)

                test_loss += loss.item()
                _, predicted = outputs.max(1)
                total += targets.size(0)
                if str(self.criterion) != "CrossEntropyLoss()":
                    _, targets= targets.max(1)

                correct += predicted.eq(targets).sum().item()

            print( 'Test Acc: %.3f%% (%d/%d)' % (100.*correct/total, correct, total))

        return 1.*correct/total
          
def get_acc_gap(MODEL_SAVE_PATH):
    
    pattern = MODEL_SAVE_PATH + "_accs_*.csv"
    # print("Looking for acc_gap CSVs with pattern:", pattern)
    csv_files = glob.glob(pattern)
    if not csv_files:
        raise FileNotFoundError(f"No accs CSV found {pattern}, Please train traget model first \n ")
    latest_csv = max(csv_files, key=os.path.getmtime)
    print(f"Loading overfitting (acc_gap) from {latest_csv}")

    df = pd.read_csv(latest_csv)
    acc_gap = df['overfitting'].iloc[-1]
    # print(f"Acc gap: {acc_gap}")
    return acc_gap 
    
def get_ent_lr(acc_gap, max_lr=0.005, k=10, mid=0.5):
    return max_lr * (1 - 1 / (1 + np.exp(-k * (acc_gap - mid))))

def get_cs_lr(acc_gap, max_lr=0.01, k=10, mid=0.5):
    return max_lr * (1 - 1 / (1 + np.exp(-k * (acc_gap - mid))))

def sigmoid_adaptive_lr(gap, mid_gap=0.475, gap_range=0.55, max_lr=0.1, min_lr=0.001):
    """
    Adaptive sigmoid-based learning rate scheduler.

    Parameters:
    - gap (float): Accuracy gap (0 to 1 scale)
    - mid_gap (float): Center point of the sigmoid (e.g., 0.475 for 47.5%)
    - gap_range (float): Controls steepness (difference between upper and lower bounds; smaller = steeper)
    - max_lr (float): Maximum learning rate
    - min_lr (float): Minimum learning rate

    Returns:
    - lr (float): Adapted learning rate
    """
    k = 10 / gap_range  # Steepness from gap_range (e.g., 0.55 gives k ≈ 18.18)
    sigmoid = 1 / (1 + np.exp(-k * (gap - mid_gap)))
    return min_lr + (max_lr - min_lr) * sigmoid

def sigmoid_adaptive_lr(gap, mid_gap=0.45, gap_range=0.65, max_lr=0.1, min_lr=0.003):
    k = 10 / gap_range  # Controls steepness
    sigmoid = 1 / (1 + np.exp(-k * (gap - mid_gap)))
    return min_lr + (max_lr - min_lr) * sigmoid

class attack_for_blackbox_com_NEW():
    def __init__(self,TARGET_PATH, SHADOW_PATH, Perturb_MODELS_PATH, ATTACK_SETS,ATTACK_SETS_PV_CSV, attack_train_loader, attack_test_loader, target_model,shadow_model,  attack_model, perturb_model, device, dataset_name, attack_name, num_classes, acc_gap):
        self.device = device

        self.TARGET_PATH = TARGET_PATH
        self.SHADOW_PATH = SHADOW_PATH
        self.ATTACK_SETS = ATTACK_SETS
        self.ATTACK_SETS_PV_CSV = ATTACK_SETS_PV_CSV
        
        self.target_model = target_model.to(self.device)
        self.shadow_model = shadow_model.to(self.device)
        self.Perturb_MODELS_PATH = Perturb_MODELS_PATH
        self.attack_name = attack_name
        print( 'self.TARGET_PATH: %s' % self.TARGET_PATH)
    
        self.num_classes = num_classes
        self.target_model.load_state_dict(torch.load(self.TARGET_PATH, weights_only=True))
        self.shadow_model.load_state_dict(torch.load(self.SHADOW_PATH, weights_only=True))

        self.target_model.eval()
        self.shadow_model.eval()
        self.member_mean = 0.0
        self.member_std = 0.0
        self.non_member_mean = 0.0
        self.non_member_std  = 0.0

        self.attack_train_loader = attack_train_loader
        self.attack_test_loader = attack_test_loader

        self.attack_model = attack_model.to(self.device)
        self.perturb_model = perturb_model.to(self.device)
        self.patience = 20
        self.early_stopping = EarlyStopping(self.patience, verbose=True)
    
        self.attack_model.apply(weights_init)
        self.perturb_model.apply(weights_init)
  
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = optim.Adam(self.attack_model.parameters(), lr=1e-3)
        self.optimizer_perturb = optim.Adam(self.perturb_model.parameters(), lr=1e-3) # need to change the learning rate to see the effect latter
        
        

        self.dataset_name = dataset_name
    
      
       
        dataset_k_values = {
            "stl10": 1000.0,
            "cifar100": 1000.0,
            # "location": 1000.0,
            "fmnist": 1000000.0,
            "purchase": 1000000.0,
            "cifar10": 10000.0,
            "utkface": 1000000,
            "texas": 10000,
            "adult": 1000000,
        }

        self.k = dataset_k_values.get(dataset_name)  # Default to 1000000 if dataset_name is not found
    
        if dataset_name == "fmnist" or dataset_name == "cifar10" or dataset_name == "utkface":
            self.k1 = 1000000.0
        else:
            self.k1 = 10.0

        # NON-image datasets
        if dataset_name == "location":
            self.k = 1000.0
            self.k1 = 10000.0   
        if dataset_name == "texas":
            self.k = 10000.0
            self.k1 = 10.0
        if dataset_name == "adult":
            self.k = 1000000.0
            self.k1 = 100.0
        if dataset_name == "purchase":
            self.k = 1000000.0
            self.k1 = 100.0 
        

        # Image datasets
        if dataset_name == "stl10":
            self.k = 1000.0
            self.k1 = 10.0
        elif dataset_name == "cifar100":
            self.k = 1000.0
            self.k1 = 10.0
        elif dataset_name == "cifar10":
            self.k = 10000.0
            self.k1 = 1000000.0 
        elif dataset_name == "utkface":
            self.k = 1000000.0
            self.k1 = 1000000.0
        elif dataset_name == "fmnist":
            self.k = 1000000.0
            self.k1 = 1000000.0
        
    
    
        # Note: The following has been used as fixed optimized rates to generate results in the paper
        if dataset_name == "cifar100":
            cs_lr = 0.01
            ent_lr = 0.1
        elif dataset_name == "cifar10":
            cs_lr = 0.01
            ent_lr = 0.001
        elif dataset_name == "fmnist":
            cs_lr = 0.01
            ent_lr = 0.001
        elif dataset_name == "utkface":
            cs_lr = 0.01
            ent_lr = 0.001
        elif dataset_name == "purchase":
            cs_lr = 0.01 # was 0.001 both
            ent_lr = 0.01
        elif dataset_name == "location":
            cs_lr = 0.01
            ent_lr = 0.01
        elif dataset_name == "adult":
            cs_lr = 0.01
            ent_lr = 0.01 # was 0.1
        elif dataset_name == "texas":
            cs_lr = 0.001
            ent_lr = 0.001
        else: # stl10
            cs_lr = 0.01
            ent_lr = 0.001


        

        self.cosine_threshold = nn.Parameter(torch.tensor(0.5, device=self.device))
        self.Entropy_quantile_threshold = nn.Parameter(torch.tensor(0.5, device=self.device))


        self.optimizer_cosine = optim.Adam([self.cosine_threshold], cs_lr)
        self.optimizer_quantile_threshold = optim.Adam([self.Entropy_quantile_threshold], lr=ent_lr)

        self.kl_threshold = torch.nn.Parameter(torch.tensor(0.5))
        kl_lr = 0.01
        self.optimizer_kl = torch.optim.Adam([self.kl_threshold], kl_lr)
 
    def _get_data(self, model, inputs, targets):
        
        result = model(inputs)
        output = F.softmax(result, dim=1)
        _, predicts = result.max(1)

        prediction = predicts.eq(targets).float()
        
        

        return output, prediction.unsqueeze(-1)

    def prepare_dataset_analyse(self):
        print("Preparing  and analysing the dataset")
        
        
        # Save train dataset to CSV
        with open(self.ATTACK_SETS_PV_CSV, "w", newline='') as f:
            writer = csv.writer(f)
           
            num_output_classes = 10  # Assuming output size is [batch_size, num_classes]
            header = ["Output_" + str(i) for i in range(num_output_classes)] + ["Prediction", "Members", "Targets"]
            writer.writerow(header)
           
            
            for inputs, targets, members in self.attack_train_loader:
                inputs, targets = inputs.to(self.device), targets.to(self.device)
                if 1:
                    output, prediction = self._get_data(self.shadow_model, inputs, targets)

                    # Write each batch as rows in the CSV file
                    for i in range(output.shape[0]):
                        # Unpack the output (PV) to individual elements
                        row = output[i].cpu().tolist() + [  # Unpacking the prediction vector (each element becomes a column)
                            prediction[i].item(),           # Correct or wrong (0/1)
                            members[i].item(),              # Membership (0/1)
                            targets[i].item()               # Target label
                        ]
                        writer.writerow(row)

        print("Finished Saving Train Dataset")
 
    def prepare_dataset(self):
        print("Preparing dataset")
        with open(self.ATTACK_SETS + "train.p", "wb") as f:
            for inputs, targets, members in self.attack_train_loader:
                inputs, targets = inputs.to(self.device), targets.to(self.device)
                if inputs.size()[0] == 64:
                    
                    # change the self.shadow_model to self.target_model to get the PVs assuming shadow model performance is the same as the target model
                    output, prediction = self._get_data(self.target_model, inputs, targets)
                   
                    pickle.dump((output, prediction, members, targets), f)
                else:
                    print("skipping: ",inputs.size()[0])


        

        print("Finished Saving Train Dataset")
    

        with open(self.ATTACK_SETS + "test.p", "wb") as f:
            for inputs, targets, members in self.attack_test_loader:
                inputs, targets = inputs.to(self.device), targets.to(self.device)
                if inputs.size()[0] == 64:
                    
                    output, prediction = self._get_data(self.target_model, inputs, targets)
                    # output = output.cpu().detach().numpy()
                
                    pickle.dump((output, prediction, members, targets), f)
                else:
                     print("test data skipping: ",inputs.size()[0])
        
        
        
        self.dataset = AttackDataset(self.ATTACK_SETS + "train.p")



        print("Finished Saving Test Dataset")
        return self.dataset
       
 
    def contrastive_loss(self, embeddings, labels, margin):
        """
        A simple contrastive loss function.
        For a pair of embeddings, if they belong to the same class (both member or both non-member),
        the target is 1 (and we penalize a large distance);
        if they belong to different classes, the target is -1 (and we penalize similarity if too high).
        
        This implementation computes the loss over all pairs in the batch.
        
        Args:
            embeddings: Tensor of shape (N, D) where N is batch size and D is embedding dimension.
            labels: Binary labels of shape (N,) indicating membership (1 for member, 0 for non-member).
            margin: Margin for dissimilar pairs.
        
        Returns:
            A scalar contrastive loss value.
        """
        # Normalize embeddings to unit vectors
        embeddings = F.normalize(embeddings, p=2, dim=1)
        
        # Compute pairwise cosine similarity matrix
        cosine_sim = torch.matmul(embeddings, embeddings.t())  # shape: (N, N)
        
        # Create label matrix: 1 if same class, -1 if different
        labels = labels.unsqueeze(1)  # shape (N, 1)
        label_matrix = (labels == labels.t()).float()
        # Convert same/different to targets of 1 and -1
        target = label_matrix * 2 - 1  # 1 for same, -1 for different
        
        # For same pairs, we want cosine similarity to be close to 1,
        # for different pairs, we want similarity to be at most a margin.
        # One simple loss is mean squared error from target:
        loss_same = F.mse_loss(cosine_sim * (target==1).float(), torch.ones_like(cosine_sim) * (target==1).float())
        # For different pairs, we want the cosine similarity to be less than some margin.
        # If similarity > margin, we incur a loss.
        diff_sim = cosine_sim * (target==-1).float()
        loss_diff = F.relu(diff_sim - margin).pow(2).mean()
        
        return loss_same + loss_diff

    # -------------------------
    # Training Function
    # -------------------------
    def train(self, epoch, result_path, result_path_csv, mode):
        self.attack_model.train()
        self.perturb_model.train()

        batch_idx = 1
        train_loss = 0
        correct = 0
        prec = 0
        recall = 0
        total = 0

        bcm = BinaryConfusionMatrix().to(self.device)
        final_train_gndtrth = []
        final_train_predict = []
        final_train_probabe = []
        final_result = []

        lambda_contrast = 0.5  # Weight for the contrastive loss term; adjust as necessary

        # Open your training data file
        with open(self.ATTACK_SETS + "train.p", "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break

                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)
                # targets can remain on CPU or be moved if needed

                if self.attack_name == "apcmia":
                    # -- Your code for perturbation using cosine similarity, entropy etc. --
                    # This block remains as before.
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]

                        # Overlap detection via cosine similarity:
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),
                            member_pvs.unsqueeze(0),
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * self.k1
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]

                        alpha = 1

                        # Entropy step:
                        epsilon = 1e-10
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * \
                                                self.perturb_model(non_member_pvs, targets[non_member_indices])
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * \
                                                    self.perturb_model(non_member_pvs, targets[non_member_indices])
                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    # Forward pass through the attack model:
                    results = self.attack_model(perturbed_pvs, prediction, targets) #with perturbation
                    # results = self.attack_model(output, prediction, targets) # without perturbation

                    # # NOTE: the constastive loss part is commented out and also the from the total loss., 
                    # # # --- Extract embeddings for contrastive loss ---
                    # # # Here, we assume your attack model has a method get_embeddings() that returns
                    # # # a feature embedding for each sample.
                    margin=0.5
                    # # embeddings = self.attack_model.get_embeddings(output, prediction, targets) # without perturbation
                    embeddings = self.attack_model.get_embeddings(perturbed_pvs, prediction, targets) # with perturbation

                    # # # Contrastive loss using the embeddings.
                    contrast_loss = self.contrastive_loss(embeddings, members, margin)

                 
                else:
                    results = self.attack_model(output, prediction, targets)
                    contrast_loss = 0  # no contrastive loss for non-apcmia attacks

                # Compute primary loss (attack loss)
                attack_loss = self.criterion(results, members)
                # total_loss = attack_loss #  without Constrastive loss 
                total_loss = attack_loss + lambda_contrast * contrast_loss #  with Contrastive loss


                # total_loss = attack_loss

                # Backpropagation
                self.optimizer.zero_grad()
                self.optimizer_perturb.zero_grad()
                self.optimizer_cosine.zero_grad()
                self.optimizer_quantile_threshold.zero_grad()

                total_loss.backward(retain_graph=True)
                self.optimizer.step()
                self.optimizer_perturb.step()
                self.optimizer_quantile_threshold.step()
                self.optimizer_cosine.step()

                train_loss += attack_loss.item()
                _, predicted = results.max(1)
                total += members.size(0)
                correct += predicted.eq(members).sum().item()

                conf_mat = bcm(predicted, members)
                prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                final_train_gndtrth.append(members)
                final_train_predict.append(predicted)
                final_train_probabe.append(results[:, 1])

                batch_idx += 1

        # Post Epoch Evaluation
        final_train_gndtrth = torch.cat(final_train_gndtrth, dim=0).cpu().detach().numpy()
        final_train_predict = torch.cat(final_train_predict, dim=0).cpu().detach().numpy()
        final_train_probabe = torch.cat(final_train_probabe, dim=0).cpu().detach().numpy()

        train_f1_score = f1_score(final_train_gndtrth, final_train_predict)
        train_roc_auc_score = roc_auc_score(final_train_gndtrth, final_train_probabe)

        final_result = [
            100. * correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            train_f1_score,
            train_roc_auc_score,
        ]

        # (Saving results code omitted for brevity)
        print(f"Train Acc: {100.*correct/total:.3f}% ({correct}/{total}) | Loss: {train_loss/batch_idx:.3f} "
            f"Precision: {100.*prec/batch_idx:.3f} Recall: {100.*recall/batch_idx:.3f}")
        
        ent_thre = torch.sigmoid(self.Entropy_quantile_threshold)
        cos_thre = torch.sigmoid(self.cosine_threshold)

        if self.attack_name == "apcmia":
            print(f"CosineT: {cos_thre:.4f}, Quantile Threshold: {ent_thre:.4f}")
     
        return cos_thre, ent_thre
    
    # -------------------------
    # Test Function
    # -------------------------
    def test(self, epoch_flag, result_path, mode):
        self.attack_model.eval()
        self.perturb_model.eval()

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device.
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    # targets can remain on CPU or be moved if needed.
                    if self.attack_name == "apcmia": #new

                        # Create masks for members and non-members.
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            # Get indices for members and non-members.
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            # Extract PVs.
                            member_pvs = output[member_indices]       # (n_members, C)
                            non_member_pvs = output[non_member_indices] # (n_non_members, C)

                            # ----- Step 2: Overlap Detection via Cosine Similarity -----
                            cos_sim = F.cosine_similarity(
                                non_member_pvs.unsqueeze(1),  # (n_non_members, 1, C)
                                member_pvs.unsqueeze(0),      # (1, n_members, C)
                                dim=2
                            )
                            max_cos_sim, _ = cos_sim.max(dim=1)  # (n_non_members,)

                            # ----- Step 3: Differentiable Binary Selection using Gumbel–Softmax -----
                            temperature = self.k1  # scaling factor for logits
                            tau = 0.5           # Gumbel–Softmax temperature
                            # Reparameterize the cosine threshold to (0,1)
                            cosine_threshold = torch.sigmoid(self.cosine_threshold)
                            logits = (max_cos_sim - cosine_threshold) * temperature  # (n_non_members,)
                            binary_logits = torch.stack([-logits, logits], dim=1)  # (n_non_members, 2)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]  # (n_non_members,)

                            alpha = 1.0

                            # ----- Step 4: Perturbation with Entropy Filtering -----
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            # Compute tentative perturbed outputs.
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            # Compute entropy for each tentative perturbed PV.
                            epsilon = 1e-10
                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1).to(self.device)  # (n_non_members,)

                            # Select top samples based on entropy.
                            # For example, use a quantile threshold (self.Entropy_quantile_threshold should be a float in (0,1)).
                            # quantile_val = torch.quantile(entropy, 0.25)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            # Use a sigmoid to create a soft entropy mask.
                            # self.k controls the steepness (if not defined, default to 50.0).
                            # k = self.k if hasattr(self, "k") else 50.0
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)

                            # Combine the binary selection with the entropy mask.
                            final_selection = binary_selection * entropy_mask
                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            # Replace non-member PVs in the overall output.
                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        # ----- Step 5: Normalize and Clip Perturbed PVs -----
                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        # ----- Step 6: Forward Pass through the Attack Model -----
                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)
        if epoch_flag:
                fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)
        else:
            fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)

        
        
        # roc_auc = auc(fpr, tpr)
        avg_test_loss = total_test_loss / batch_idx
        
        final_result.extend([
        correct / total,
        (prec / batch_idx).item(),
        (recall / batch_idx).item(),
        test_f1_score,
        test_roc_auc_score,
        avg_test_loss  # Append average test loss
        ])

        with open(result_path, "wb") as f_out:
            pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        
        print(f"Test Acc: {100.*correct/(1.0*total):.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, precision: {100.*prec/(1.0*batch_idx):.3f}, recall: {100.*recall/batch_idx:.3f}")

        
        # here unload the full test.p and 
        return final_result, fpr, tpr
    
    def train_KL(self, epoch, result_path, result_path_csv, mode):
        self.attack_model.train()
        self.perturb_model.train()

        batch_idx = 1
        train_loss = 0
        correct = 0
        prec = 0
        recall = 0
        total = 0

        bcm = BinaryConfusionMatrix().to(self.device)
        final_train_gndtrth = []
        final_train_predict = []
        final_train_probabe = []
        final_result = []

        lambda_contrast = 0.5  # Weight for the contrastive loss term

        with open(self.ATTACK_SETS + "train.p", "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break

                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)

                if self.attack_name == "apcmia":
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]

                        # KL divergence similarity
                        epsilon = 1e-8
                        p = non_member_pvs.unsqueeze(1).clamp(min=epsilon, max=1)
                        q = member_pvs.unsqueeze(0).clamp(min=epsilon, max=1)

                        kl_div = (p * (p / q).log()).sum(dim=2)
                        min_kl_div, _ = kl_div.min(dim=1)

                        tau = 0.5
                        kl_threshold = torch.sigmoid(self.kl_threshold)
                        logits = (kl_threshold - min_kl_div) * self.k1
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]

                        alpha = 1
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * \
                                            self.perturb_model(non_member_pvs, targets[non_member_indices])
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        final_selection = binary_selection * entropy_mask

                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * \
                                                self.perturb_model(non_member_pvs, targets[non_member_indices])

                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    results = self.attack_model(perturbed_pvs, prediction, targets)

                    margin = 0.5
                    embeddings = self.attack_model.get_embeddings(perturbed_pvs, prediction, targets)
                    contrast_loss = self.contrastive_loss(embeddings, members, margin)

                else:
                    results = self.attack_model(output, prediction, targets)
                    contrast_loss = 0

                attack_loss = self.criterion(results, members)
                total_loss = attack_loss + lambda_contrast * contrast_loss

                self.optimizer.zero_grad()
                self.optimizer_perturb.zero_grad()
                self.optimizer_kl.zero_grad()
                self.optimizer_quantile_threshold.zero_grad()

                total_loss.backward(retain_graph=True)
                self.optimizer.step()
                self.optimizer_perturb.step()
                self.optimizer_quantile_threshold.step()
                self.optimizer_kl.step()

                train_loss += attack_loss.item()
                _, predicted = results.max(1)
                total += members.size(0)
                correct += predicted.eq(members).sum().item()

                conf_mat = bcm(predicted, members)
                prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                final_train_gndtrth.append(members)
                final_train_predict.append(predicted)
                final_train_probabe.append(results[:, 1])

                batch_idx += 1

        final_train_gndtrth = torch.cat(final_train_gndtrth, dim=0).cpu().detach().numpy()
        final_train_predict = torch.cat(final_train_predict, dim=0).cpu().detach().numpy()
        final_train_probabe = torch.cat(final_train_probabe, dim=0).cpu().detach().numpy()

        train_f1_score = f1_score(final_train_gndtrth, final_train_predict)
        train_roc_auc_score = roc_auc_score(final_train_gndtrth, final_train_probabe)

        final_result = [
            100. * correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            train_f1_score,
            train_roc_auc_score,
        ]

        print(f"Train Acc: {100.*correct/total:.3f}% ({correct}/{total}) | Loss: {train_loss/batch_idx:.3f} "
            f"Precision: {100.*prec/batch_idx:.3f} Recall: {100.*recall/batch_idx:.3f}")
        print(f"KL Threshold: {self.kl_threshold.item():.4f}, Quantile Threshold: {self.Entropy_quantile_threshold.item():.4f}")

        return self.kl_threshold.item(), self.Entropy_quantile_threshold.item()

    def train_ecld(self, epoch, result_path, result_path_csv, mode): 
        
        self.attack_model.train()
        self.perturb_model.train()

        batch_idx = 1
        train_loss = 0
        correct = 0
        prec = 0
        recall = 0
        total = 0

        bcm = BinaryConfusionMatrix().to(self.device)
        final_train_gndtrth = []
        final_train_predict = []
        final_train_probabe = []
        final_result = []

        lambda_contrast = 0.5  # Weight for the contrastive loss term; adjust as necessary

        # Open your training data file
        with open(self.ATTACK_SETS + "train.p", "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break

                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)
                # targets can remain on CPU or be moved if needed

                if self.attack_name == "apcmia":
                    # --- Perturbation using negative Euclidean distance instead of cosine similarity ---
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]       # (n_members, C)
                        non_member_pvs = output[non_member_indices] # (n_non_members, C)

                        # Compute pairwise Euclidean distances: shape (n_non_members, n_members)
                        distances = torch.cdist(non_member_pvs, member_pvs, p=2)
                        # Convert distances to similarity scores (smaller distance -> higher similarity)
                        euclid_sim = -distances
                        # For each non-member, select maximum similarity (i.e. the most similar member)
                        max_sim, _ = euclid_sim.max(dim=1)  # (n_non_members,)

                        tau = 0.5
                        # Use a learnable threshold (same parameter reused; can be renamed)
                        similarity_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_sim - similarity_threshold) * self.k1
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]
                        
                        alpha = 1

                        # --- Entropy-Based Weighting ---
                        epsilon = 1e-10
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * \
                                                self.perturb_model(non_member_pvs, targets[non_member_indices])
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * \
                                                    self.perturb_model(non_member_pvs, targets[non_member_indices])
                        
                        # Replace non-member PVs in output with perturbed values.
                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    # Normalize the perturbed probability vectors:
                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    # Forward pass through the attack model:
                    results = self.attack_model(perturbed_pvs, prediction, targets) # Using original output (or you can try perturbed_pvs)

                    # --- Contrastive Loss ---
                    margin = 0.5
                    embeddings = self.attack_model.get_embeddings(perturbed_pvs, prediction, targets)
                    contrast_loss = self.contrastive_loss(embeddings, members, margin)
                else:
                    results = self.attack_model(output, prediction, targets)
                    contrast_loss = 0  # no contrastive loss for non-apcmia attacks

                # Compute primary loss (attack loss)
                attack_loss = self.criterion(results, members)
                total_loss = attack_loss + lambda_contrast * contrast_loss 

                # Backpropagation
                self.optimizer.zero_grad()
                self.optimizer_perturb.zero_grad()
                self.optimizer_cosine.zero_grad()
                self.optimizer_quantile_threshold.zero_grad()

                total_loss.backward(retain_graph=True)

                # print(f"Grad of cosine_threshold: {self.cosine_threshold.grad}")

                self.optimizer.step()
                self.optimizer_perturb.step()
                self.optimizer_quantile_threshold.step()
                self.optimizer_cosine.step()

                # print(f"Grad of cosine_threshold: {self.cosine_threshold.grad}")

                train_loss += attack_loss.item()
                _, predicted = results.max(1)
                total += members.size(0)
                correct += predicted.eq(members).sum().item()

                conf_mat = bcm(predicted, members)
                prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                final_train_gndtrth.append(members)
                final_train_predict.append(predicted)
                final_train_probabe.append(results[:, 1])

                batch_idx += 1

        # Post Epoch Evaluation
        final_train_gndtrth = torch.cat(final_train_gndtrth, dim=0).cpu().detach().numpy()
        final_train_predict = torch.cat(final_train_predict, dim=0).cpu().detach().numpy()
        final_train_probabe = torch.cat(final_train_probabe, dim=0).cpu().detach().numpy()

        train_f1_score = f1_score(final_train_gndtrth, final_train_predict)
        train_roc_auc_score = roc_auc_score(final_train_gndtrth, final_train_probabe)

        final_result = [
            100. * correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            train_f1_score,
            train_roc_auc_score,
        ]

        print(f"Train Acc: {100.*correct/total:.3f}% ({correct}/{total}) | Loss: {train_loss/batch_idx:.3f} "
            f"Precision: {100.*prec/batch_idx:.3f} Recall: {100.*recall/batch_idx:.3f}")
        print(f"Cosine Threshold: {torch.sigmoid(self.cosine_threshold).item():.4f}, Quantile Threshold: {torch.sigmoid(self.Entropy_quantile_threshold).item():.4f}")
        # print(f"Cosine Threshold (sigmoid): {torch.sigmoid(self.cosine_threshold).item():.4f}")
        # print(f"Quantile Threshold (sigmoid): {torch.sigmoid(self.Entropy_quantile_threshold).item():.4f}")

        return self.cosine_threshold.item(), self.Entropy_quantile_threshold.item()

    def test_KL(self, epoch_flag, result_path, mode):
        self.attack_model.eval()
        self.perturb_model.eval()

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)

                    if self.attack_name == "apcmia":
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            member_pvs = output[member_indices]
                            non_member_pvs = output[non_member_indices]

                            # ----- KL Divergence Similarity -----
                            epsilon = 1e-8
                            p = non_member_pvs.unsqueeze(1).clamp(min=epsilon, max=1)
                            q = member_pvs.unsqueeze(0).clamp(min=epsilon, max=1)

                            kl_div = (p * (p / q).log()).sum(dim=2)  # shape: [n_non_members, n_members]
                            min_kl_div, _ = kl_div.min(dim=1)

                            # ----- Gumbel-Softmax Selection -----
                            tau = 0.5
                            kl_threshold = torch.sigmoid(self.kl_threshold)
                            logits = (kl_threshold - min_kl_div) * self.k1
                            binary_logits = torch.stack([-logits, logits], dim=1)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]

                            # ----- Entropy Filtering & Perturbation -----
                            alpha = 1.0
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                            final_selection = binary_selection * entropy_mask

                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        # ----- Normalize & Clip -----
                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post-Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)
        fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx
        final_result.extend([
            correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            test_f1_score,
            test_roc_auc_score,
            avg_test_loss
        ])

        with open(result_path, "wb") as f_out:
            pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        print(f"Test Acc: {100.*correct/(1.0*total):.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, "
            f"precision: {100.*prec/(1.0*batch_idx):.3f}, recall: {100.*recall/batch_idx:.3f}")

        return final_result, fpr, tpr

    def test_ecld(self, epoch_flag, result_path, mode):
        self.attack_model.eval()
        self.perturb_model.eval()

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)

                    if self.attack_name == "apcmia":
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            member_pvs = output[member_indices]
                            non_member_pvs = output[non_member_indices]

                            # ----- Euclidean Similarity -----
                            distances = torch.cdist(non_member_pvs, member_pvs, p=2)
                            euclid_sim = -distances
                            max_sim, _ = euclid_sim.max(dim=1)

                            tau = 0.5
                            similarity_threshold = torch.sigmoid(self.cosine_threshold)
                            logits = (max_sim - similarity_threshold) * self.k1
                            binary_logits = torch.stack([-logits, logits], dim=1)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]

                            alpha = 1.0
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            epsilon = 1e-10
                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                            final_selection = binary_selection * entropy_mask

                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post-Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)
        fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx

        final_result.extend([
            correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            test_f1_score,
            test_roc_auc_score,
            avg_test_loss
        ])

        with open(result_path, "wb") as f_out:
            pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        print(f"Test Acc: {100.*correct/(1.0*total):.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, "
            f"precision: {100.*prec/(1.0*batch_idx):.3f}, recall: {100.*recall/batch_idx:.3f}")

        return final_result, fpr, tpr

    def train_pearson(self, epoch, result_path, result_path_csv, mode): 
        self.attack_model.train()
        self.perturb_model.train()

        batch_idx = 1
        train_loss = 0
        correct = 0
        prec = 0
        recall = 0
        total = 0

        bcm = BinaryConfusionMatrix().to(self.device)
        final_train_gndtrth = []
        final_train_predict = []
        final_train_probabe = []
        final_result = []

        lambda_contrast = 0.5  # Weight for contrastive loss

        with open(self.ATTACK_SETS + "train.p", "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break

                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)

                if self.attack_name == "apcmia":
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)

                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]         # (m, C)
                        non_member_pvs = output[non_member_indices] # (n, C)

                        # Normalize PVs: subtract mean
                        member_mean = member_pvs.mean(dim=1, keepdim=True)
                        member_std = member_pvs.std(dim=1, unbiased=False, keepdim=True) + 1e-8
                        member_norm = (member_pvs - member_mean) / member_std  # (m, C)

                        non_member_mean = non_member_pvs.mean(dim=1, keepdim=True)
                        non_member_std = non_member_pvs.std(dim=1, unbiased=False, keepdim=True) + 1e-8
                        non_member_norm = (non_member_pvs - non_member_mean) / non_member_std  # (n, C)

                        # Compute Pearson correlation (dot product after normalization)
                        pearson_corr = torch.matmul(non_member_norm, member_norm.T) / non_member_norm.size(1)  # (n, m)
                        max_corr, _ = pearson_corr.max(dim=1)  # Most similar member for each non-member

                        # Use threshold and gumbel-softmax to determine which non-members to perturb
                        tau = 0.5
                        pearson_threshold = torch.sigmoid(self.cosine_threshold)  # reuse threshold param
                        logits = (max_corr - pearson_threshold) * self.k1
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]  # (n,)

                        # Apply perturbation
                        alpha = 1
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                        # Entropy-based filtering
                        epsilon = 1e-10
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        final_selection = binary_selection * entropy_mask

                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    # Normalize & forward pass
                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    results = self.attack_model(perturbed_pvs, prediction, targets)

                    # Contrastive Loss
                    margin = 0.5
                    embeddings = self.attack_model.get_embeddings(perturbed_pvs, prediction, targets)
                    contrast_loss = self.contrastive_loss(embeddings, members, margin)

                else:
                    results = self.attack_model(output, prediction, targets)
                    contrast_loss = 0

                attack_loss = self.criterion(results, members)
                total_loss = attack_loss + lambda_contrast * contrast_loss

                self.optimizer.zero_grad()
                self.optimizer_perturb.zero_grad()
                self.optimizer_cosine.zero_grad()
                self.optimizer_quantile_threshold.zero_grad()

                total_loss.backward(retain_graph=True)
                self.optimizer.step()
                self.optimizer_perturb.step()
                self.optimizer_quantile_threshold.step()
                self.optimizer_cosine.step()

                train_loss += attack_loss.item()
                _, predicted = results.max(1)
                total += members.size(0)
                correct += predicted.eq(members).sum().item()

                conf_mat = bcm(predicted, members)
                prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                final_train_gndtrth.append(members)
                final_train_predict.append(predicted)
                final_train_probabe.append(results[:, 1])

                batch_idx += 1

        final_train_gndtrth = torch.cat(final_train_gndtrth, dim=0).cpu().detach().numpy()
        final_train_predict = torch.cat(final_train_predict, dim=0).cpu().detach().numpy()
        final_train_probabe = torch.cat(final_train_probabe, dim=0).cpu().detach().numpy()

        train_f1_score = f1_score(final_train_gndtrth, final_train_predict)
        train_roc_auc_score = roc_auc_score(final_train_gndtrth, final_train_probabe)

        final_result = [
            100. * correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            train_f1_score,
            train_roc_auc_score,
        ]

        print(f"Train Acc: {100.*correct/total:.3f}% ({correct}/{total}) | Loss: {train_loss/batch_idx:.3f} "
            f"Precision: {100.*prec/batch_idx:.3f} Recall: {100.*recall/batch_idx:.3f}")
        print(f"Pearson Threshold (used): {torch.sigmoid(self.cosine_threshold).item():.4f}, "
            f"Quantile Threshold: {torch.sigmoid(self.Entropy_quantile_threshold).item():.4f}")

        return self.cosine_threshold.item(), self.Entropy_quantile_threshold.item()
    
    def test_pearson(self, epoch_flag, result_path, mode):
        self.attack_model.eval()
        self.perturb_model.eval()

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)

                    if self.attack_name == "apcmia":
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            member_pvs = output[member_indices]
                            non_member_pvs = output[non_member_indices]

                            # Pearson similarity calculation
                            member_mean = member_pvs.mean(dim=1, keepdim=True)
                            member_std = member_pvs.std(dim=1, unbiased=False, keepdim=True) + 1e-8
                            member_norm = (member_pvs - member_mean) / member_std

                            non_member_mean = non_member_pvs.mean(dim=1, keepdim=True)
                            non_member_std = non_member_pvs.std(dim=1, unbiased=False, keepdim=True) + 1e-8
                            non_member_norm = (non_member_pvs - non_member_mean) / non_member_std

                            pearson_corr = torch.matmul(non_member_norm, member_norm.T) / non_member_norm.size(1)
                            max_corr, _ = pearson_corr.max(dim=1)

                            # Gumbel-softmax selection
                            tau = 0.5
                            pearson_threshold = torch.sigmoid(self.cosine_threshold)
                            logits = (max_corr - pearson_threshold) * self.k1
                            binary_logits = torch.stack([-logits, logits], dim=1)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]

                            # Entropy-filtered perturbation
                            alpha = 1.0
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            epsilon = 1e-10
                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                            final_selection = binary_selection * entropy_mask

                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)
        fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx

        final_result.extend([
            correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            test_f1_score,
            test_roc_auc_score,
            avg_test_loss
        ])

        with open(result_path, "wb") as f_out:
            pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        print(f"Test Acc: {100.*correct/total:.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, "
            f"Precision: {100.*prec/batch_idx:.3f}, Recall: {100.*recall/batch_idx:.3f}")

        return final_result, fpr, tpr

    def train_mahalanobis(self, epoch, result_path, result_path_csv, mode): 
        self.attack_model.train()
        self.perturb_model.train()

        batch_idx = 1
        train_loss = 0
        correct = 0
        prec = 0
        recall = 0
        total = 0

        bcm = BinaryConfusionMatrix().to(self.device)
        final_train_gndtrth = []
        final_train_predict = []
        final_train_probabe = []
        final_result = []

        lambda_contrast = 0.5  # Weight for contrastive loss

        with open(self.ATTACK_SETS + "train.p", "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break

                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)

                if self.attack_name == "apcmia":
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)

                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]         # (m, C)
                        non_member_pvs = output[non_member_indices] # (n, C)

                        # --- Compute Covariance Matrix for Member PVs ---
                        member_mean = member_pvs.mean(dim=0, keepdim=True)  # (1, C)
                        centered_member = member_pvs - member_mean
                        cov = centered_member.T @ centered_member / (member_pvs.size(0) - 1)  # (C, C)

                        # Invert covariance matrix (or use pseudo-inverse if singular)
                        try:
                            cov_inv = torch.inverse(cov)
                        except RuntimeError:
                            cov_inv = torch.pinverse(cov)

                        # --- Mahalanobis Distance: Each non-member to each member ---
                        delta = non_member_pvs.unsqueeze(1) - member_pvs.unsqueeze(0)  # (n, m, C)
                        dists = torch.einsum("nmc,cd,nmd->nm", delta, cov_inv, delta)  # (n, m)
                        mahala_sim = -dists  # Negative = similarity

                        max_sim, _ = mahala_sim.max(dim=1)  # (n,)

                        # --- Gumbel Selection ---
                        tau = 0.5
                        similarity_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_sim - similarity_threshold) * self.k1
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]

                        # --- Perturbation + Entropy Mask ---
                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                        epsilon = 1e-10
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        final_selection = binary_selection * entropy_mask

                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values
                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    # Normalize perturbed PVs
                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    results = self.attack_model(perturbed_pvs, prediction, targets)

                    # Contrastive Loss
                    margin = 0.5
                    embeddings = self.attack_model.get_embeddings(perturbed_pvs, prediction, targets)
                    contrast_loss = self.contrastive_loss(embeddings, members, margin)

                else:
                    results = self.attack_model(output, prediction, targets)
                    contrast_loss = 0

                attack_loss = self.criterion(results, members)
                total_loss = attack_loss + lambda_contrast * contrast_loss

                self.optimizer.zero_grad()
                self.optimizer_perturb.zero_grad()
                self.optimizer_cosine.zero_grad()
                self.optimizer_quantile_threshold.zero_grad()

                total_loss.backward(retain_graph=True)
                self.optimizer.step()
                self.optimizer_perturb.step()
                self.optimizer_quantile_threshold.step()
                self.optimizer_cosine.step()

                train_loss += attack_loss.item()
                _, predicted = results.max(1)
                total += members.size(0)
                correct += predicted.eq(members).sum().item()

                conf_mat = bcm(predicted, members)
                prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                final_train_gndtrth.append(members)
                final_train_predict.append(predicted)
                final_train_probabe.append(results[:, 1])

                batch_idx += 1

        final_train_gndtrth = torch.cat(final_train_gndtrth, dim=0).cpu().detach().numpy()
        final_train_predict = torch.cat(final_train_predict, dim=0).cpu().detach().numpy()
        final_train_probabe = torch.cat(final_train_probabe, dim=0).cpu().detach().numpy()

        train_f1_score = f1_score(final_train_gndtrth, final_train_predict)
        train_roc_auc_score = roc_auc_score(final_train_gndtrth, final_train_probabe)

        final_result = [
            100. * correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            train_f1_score,
            train_roc_auc_score,
        ]

        print(f"Train Acc: {100.*correct/total:.3f}% ({correct}/{total}) | Loss: {train_loss/batch_idx:.3f} "
            f"Precision: {100.*prec/batch_idx:.3f} Recall: {100.*recall/batch_idx:.3f}")
        print(f"Mahalanobis Threshold (used): {torch.sigmoid(self.cosine_threshold).item():.4f}, "
            f"Quantile Threshold: {torch.sigmoid(self.Entropy_quantile_threshold).item():.4f}")

        return self.cosine_threshold.item(), self.Entropy_quantile_threshold.item()

    def test_mahalanobis(self, epoch_flag, result_path, mode):
        self.attack_model.eval()
        self.perturb_model.eval()

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)

                    if self.attack_name == "apcmia":
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            member_pvs = output[member_indices]
                            non_member_pvs = output[non_member_indices]

                            # Compute covariance matrix from member PVs
                            member_mean = member_pvs.mean(dim=0, keepdim=True)
                            centered_member = member_pvs - member_mean
                            cov = centered_member.T @ centered_member / (member_pvs.size(0) - 1)

                            try:
                                cov_inv = torch.inverse(cov)
                            except RuntimeError:
                                cov_inv = torch.pinverse(cov)

                            # Compute Mahalanobis distance
                            delta = non_member_pvs.unsqueeze(1) - member_pvs.unsqueeze(0)  # (n, m, C)
                            dists = torch.einsum("nmc,cd,nmd->nm", delta, cov_inv, delta)  # (n, m)
                            mahala_sim = -dists  # Use as similarity

                            max_sim, _ = mahala_sim.max(dim=1)

                            # Gumbel-softmax based binary selection
                            tau = 0.5
                            similarity_threshold = torch.sigmoid(self.cosine_threshold)
                            logits = (max_sim - similarity_threshold) * self.k1
                            binary_logits = torch.stack([-logits, logits], dim=1)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]

                            alpha = 1.0
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            epsilon = 1e-10
                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                            final_selection = binary_selection * entropy_mask

                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)
        fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx

        final_result.extend([
            correct / total,
            (prec / batch_idx).item(),
            (recall / batch_idx).item(),
            test_f1_score,
            test_roc_auc_score,
            avg_test_loss
        ])

        with open(result_path, "wb") as f_out:
            pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        print(f"Test Acc: {100.*correct/total:.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, "
            f"Precision: {100.*prec/batch_idx:.3f}, Recall: {100.*recall/batch_idx:.3f}")

        return final_result, fpr, tpr
    
    def test_saved_model_apcmia(self, atk_model, prt_model, consin_thr, entrp_thr):
        
        # checkpoint = torch.load(models_path, map_location=self.device, weights_only=True)
        # self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        # self.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
        # self.cosine_threshold.data = checkpoint['cosine_threshold'].to(self.device)
        # self.Entropy_quantile_threshold.data = checkpoint['Entropy_quantile_threshold'].to(self.device)
        
        # torch.tensor(checkpoint['Entropy_quantile_threshold'], device=self.device)
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)

        # print(f"Cosine Threshold: {self.cosine_threshold.item():.4f}, Entropy Quantile Threshold: {self.Entropy_quantile_threshold.item():.4f}")
        # exit()
        # Set models to evaluation mode.
        self.attack_model.eval()
        self.perturb_model.eval()

        

        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device.
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    # targets can remain on CPU or be moved if needed.
                    if self.attack_name == "apcmia": #new

                        # Create masks for members and non-members.
                        member_mask = (members == 1)
                        non_member_mask = (members == 0)

                        if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                            # Get indices for members and non-members.
                            member_indices = member_mask.nonzero(as_tuple=True)[0]
                            non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                            # Extract PVs.
                            member_pvs = output[member_indices]       # (n_members, C)
                            non_member_pvs = output[non_member_indices] # (n_non_members, C)

                            # ----- Step 2: Overlap Detection via Cosine Similarity -----
                            cos_sim = F.cosine_similarity(
                                non_member_pvs.unsqueeze(1),  # (n_non_members, 1, C)
                                member_pvs.unsqueeze(0),      # (1, n_members, C)
                                dim=2
                            )
                            max_cos_sim, _ = cos_sim.max(dim=1)  # (n_non_members,)

                            # ----- Step 3: Differentiable Binary Selection using Gumbel–Softmax -----
                            temperature = self.k1  # scaling factor for logits
                            tau = 0.5           # Gumbel–Softmax temperature
                            # Reparameterize the cosine threshold to (0,1)
                            cosine_threshold = torch.sigmoid(self.cosine_threshold)
                            logits = (max_cos_sim - cosine_threshold) * temperature  # (n_non_members,)
                            binary_logits = torch.stack([-logits, logits], dim=1)  # (n_non_members, 2)
                            gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                            binary_selection = gumbel_selection[:, 1]  # (n_non_members,)

                            alpha = 1.0

                            # ----- Step 4: Perturbation with Entropy Filtering -----
                            learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                            # Compute tentative perturbed outputs.
                            tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                            # Compute entropy for each tentative perturbed PV.
                            epsilon = 1e-10
                            entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1).to(self.device)  # (n_non_members,)

                            # Select top samples based on entropy.
                            # For example, use a quantile threshold (self.Entropy_quantile_threshold should be a float in (0,1)).
                            # quantile_val = torch.quantile(entropy, 0.25)
                            quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                            quantile_val = torch.quantile(entropy, quantile_threshold)
                            # Use a sigmoid to create a soft entropy mask.
                            # self.k controls the steepness (if not defined, default to 50.0).
                            # k = self.k if hasattr(self, "k") else 50.0
                            entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)

                            # Combine the binary selection with the entropy mask.
                            final_selection = binary_selection * entropy_mask
                            perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                            # Replace non-member PVs in the overall output.
                            perturbed_pvs = output.clone()
                            perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                        else:
                            perturbed_pvs = output.clone()

                        # ----- Step 5: Normalize and Clip Perturbed PVs -----
                        perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                        perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                        # ----- Step 6: Forward Pass through the Attack Model -----
                        results = self.attack_model(perturbed_pvs, prediction, targets)
                    else:
                        results = self.attack_model(output, prediction, targets)

                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx
        
        


        final_result.extend([
        correct / total,
        (prec / batch_idx).item(),
        (recall / batch_idx).item(),
        test_f1_score,
        test_roc_auc_score,
        avg_test_loss  # Append average test loss
        ])

        # with open(models_apth, "wb") as f_out:
        #     pickle.dump((final_test_gndtrth, final_test_predict, final_test_probabe), f_out)

        
        print(f"Final: Test Acc: {100.*correct/(1.0*total):.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, precision: {100.*prec/(1.0*batch_idx):.3f}, recall: {100.*recall/batch_idx:.3f}")


       
        return final_result
    
    def test_saved_model_rest(self, model):
        
        # checkpoint = torch.load(models_apth, map_location=self.device, weights_only=True)
        # # Load state dictionaries for the models.
        # self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        self.attack_model = model
        # Set models to evaluation mode.
        self.attack_model.eval()
        
        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device.
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    
                    results = self.attack_model(output, prediction, targets)
                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx
        
       


        final_result.extend([
        correct / total,
        (prec / batch_idx).item(),
        (recall / batch_idx).item(),
        test_f1_score,
        test_roc_auc_score,
        avg_test_loss  # Append average test loss
        ])

        print(f"Final: Test Acc: {100.*correct/(1.0*total):.3f}% ({correct}/{total}), Loss: {avg_test_loss:.3f}, precision: {100.*prec/(1.0*batch_idx):.3f}, recall: {100.*recall/batch_idx:.3f}")

        return final_result
   
    def compute_roc_curve_rest(self, model):
        
        # checkpoint = torch.load(models_apth, map_location=self.device, weights_only=True)
        # # Load state dictionaries for the models.
        # self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        self.attack_model = model
        # Set models to evaluation mode.
        self.attack_model.eval()
        
        batch_idx = 1
        correct = 0
        total = 0
        prec = 0
        recall = 0
        total_test_loss = 0.0
        bcm = BinaryConfusionMatrix().to(self.device)

        final_test_gndtrth = []
        final_test_predict = []
        final_test_probabe = []
        final_result = []

        with torch.no_grad():
            with open(self.ATTACK_SETS + "test.p", "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device.
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    
                    results = self.attack_model(output, prediction, targets)
                    results = F.softmax(results, dim=1)
                    _, predicted = results.max(dim=1)

                    loss = self.criterion(results, members)
                    total_test_loss += loss.item()

                    total += members.size(0)
                    correct += predicted.eq(members).sum().item()

                    conf_mat = bcm(predicted, members)
                    prec += conf_mat[1, 1] / torch.sum(conf_mat[:, -1])
                    recall += conf_mat[1, 1] / torch.sum(conf_mat[-1, :])

                    final_test_gndtrth.append(members)
                    final_test_predict.append(predicted)
                    final_test_probabe.append(results[:, 1])

                    batch_idx += 1

        # ----- Post Evaluation -----
        final_test_gndtrth = torch.cat(final_test_gndtrth, dim=0).cpu().detach().numpy()
        final_test_predict = torch.cat(final_test_predict, dim=0).cpu().detach().numpy()
        final_test_probabe = torch.cat(final_test_probabe, dim=0).cpu().detach().numpy()

        test_f1_score = f1_score(final_test_gndtrth, final_test_predict)
        test_roc_auc_score = roc_auc_score(final_test_gndtrth, final_test_probabe)

        avg_test_loss = total_test_loss / batch_idx
        
       


        final_result.extend([
        correct / total,
        (prec / batch_idx).item(),
        (recall / batch_idx).item(),
        test_f1_score,
        test_roc_auc_score,
        avg_test_loss  # Append average test loss
        ])
        

        fpr, tpr, thresholds = roc_curve(final_test_gndtrth, final_test_probabe)
        roc_auc = auc(fpr, tpr)

        return fpr, tpr, thresholds, roc_auc

    def compute_roc_curve_apcmia(self, atk_model, prt_model, consin_thr, entrp_thr):
        """
        Computes the ROC curve (FPR, TPR, thresholds) and ROC AUC for the attack model,
        using the test set stored in self.ATTACK_SETS + "test.p". It follows the same
        perturbation/selection procedure as in self.test() to get final attack predictions.
        
        Args:
            plot (bool): Whether to plot the ROC curve.
            save_path (str): If provided, save the ROC plot to this file.
        
        Returns:
            fpr (np.ndarray): False positive rates.
            tpr (np.ndarray): True positive rates.
            thresholds (np.ndarray): Thresholds used.
            roc_auc (float): Area under the ROC curve.
        """

        # checkpoint = torch.load(models_apth, map_location=self.device, weights_only=True)
        # # Load state dictionaries for the models.
        # self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        # self.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
        # # Restore the learned threshold parameters.
        # self.cosine_threshold.data = checkpoint['cosine_threshold'].to(self.device)
        # self.Entropy_quantile_threshold.data = checkpoint['Entropy_quantile_threshold'].to(self.device)
        
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)
        # print(f"Cosine Threshold: {self.cosine_threshold.item():.4f}, Entropy Quantile Threshold: {self.Entropy_quantile_threshold.item():.4f}")
        # exit()

        # Set models to evaluation mode.
        self.attack_model.eval()
        self.perturb_model.eval()
        
        # # Set models to evaluation mode.
        # self.attack_model.eval()
        # self.perturb_model.eval()
        
        final_ground_truth = []
        final_probabilities = []
        
        with torch.no_grad():
            test_file = self.ATTACK_SETS + "test.p"
            with open(test_file, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device.
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    # (targets can remain on CPU if not used for perturbation)

                    # Create masks for members and non-members.
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)

                    # Compute perturbed outputs using the same procedure as in test().
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]
                        
                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]
                        
                        # Overlap detection via cosine similarity.
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),  # shape: (n_non_members, 1, C)
                            member_pvs.unsqueeze(0),      # shape: (1, n_members, C)
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)  # (n_non_members,)
                        
                        # Use Gumbel–Softmax for binary selection.
                        temperature = self.k1
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]  # (n_non_members,)
                        
                        alpha = 1.0
                        # Compute the learned perturbations.
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                        # Compute the entropy of each tentative perturbed PV.
                        epsilon = 1e-10
                        entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1)
                        
                        # Compute a quantile value from entropy.
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy, quantile_threshold)
                        # Use a differentiable (soft) mask for entropy; self.k is a steepness factor.
                        entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                        
                        # Combine binary selection with the entropy mask.
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                        # Replace the non-member PVs in the overall output.
                        perturbed_pvs = output.clone()
                        perturbed_pvs[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_pvs = output.clone()

                    # Normalize and clip the perturbed PVs.
                    perturbed_pvs = torch.clamp(perturbed_pvs, min=1e-6, max=1)
                    perturbed_pvs = perturbed_pvs / perturbed_pvs.sum(dim=1, keepdim=True)

                    # Forward pass through the attack model.
                    results = self.attack_model(perturbed_pvs, prediction, targets)
                    results = F.softmax(results, dim=1)
                    # results = self.attack_model(perturbed_pvs, prediction, targets)
                    # results = F.softmax(results, dim=1)

                    # _, predicted = results.max(dim=1)
                    # We assume that column 1 gives the probability for membership.
                    probabilities = results[:, 1]
                    # print(f"First few probabilities: {probabilities[:5]}")
                    # print(f"First few members: {members[:5]}")
                    # print(f"predicted: {predicted[:5]}")
                    # exit()

                    final_ground_truth.append(members.cpu())
                    final_probabilities.append(probabilities.cpu())
                    # exit()
            # Concatenate collected results.
            final_ground_truth = torch.cat(final_ground_truth, dim=0).numpy()
            final_probabilities = torch.cat(final_probabilities, dim=0).numpy()
        
        # Compute the ROC curve and ROC AUC.
        fpr, tpr, thresholds = roc_curve(final_ground_truth, final_probabilities)
        roc_auc = auc(fpr, tpr)

        # if plot:
        #     plt.figure(figsize=(8, 6))
        #     plt.plot(fpr, tpr, label="ROC curve (AUC = %0.2f)" % roc_auc, lw=2)
        #     plt.plot([0, 1], [0, 1], 'k--', lw=2)
        #     plt.xlim([0.0, 1.0])
        #     plt.ylim([0.0, 1.05])
        #     plt.xlabel("False Positive Rate")
        #     plt.ylabel("True Positive Rate")
        #     plt.title("Receiver Operating Characteristic")
        #     plt.legend(loc="lower right")
        #     if save_path is not None:
        #         plt.savefig(save_path)
        #     plt.show()

        return fpr, tpr, thresholds, roc_auc

    def compute_entropy_distribution_2(self, models_apth, dataset="test", plot=True, save_path=None):
        """
        Loads the saved models and thresholds from 'models_apth', then computes and (optionally)
        plots the entropy distributions of probability vectors (PVs) before and after perturbation.
        The resulting plot has two subplots:
        - Top: members vs. non-members (original entropies, before perturbation)
        - Bottom: members vs. non-members (perturbed entropies, after perturbation)
        """

        import os
        import torch
        import numpy as np
        import matplotlib.pyplot as plt
        import torch.nn.functional as F

        # 1. Load checkpoint and restore attack/perturb models + thresholds.
        checkpoint = torch.load(models_apth, map_location=self.device, weights_only=True)
        self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        self.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
        self.cosine_threshold.data = checkpoint['cosine_threshold'].to(self.device)
        self.Entropy_quantile_threshold.data = checkpoint['Entropy_quantile_threshold'].to(self.device)

        self.attack_model.eval()
        self.perturb_model.eval()

        # 2. Select the file based on dataset (train/test).
        if dataset.lower() == "test":
            file_path = self.ATTACK_SETS + "test.p"
        elif dataset.lower() == "train":
            file_path = self.ATTACK_SETS + "train.p"
        else:
            raise ValueError("Dataset must be 'test' or 'train'.")

        # We'll store four lists of entropies:
        # (a) Members' original entropies
        # (b) Non-members' original entropies
        # (c) Members' perturbed entropies
        # (d) Non-members' perturbed entropies
        members_orig_list = []
        nonmembers_orig_list = []
        members_pert_list = []
        nonmembers_pert_list = []

        epsilon = 1e-10
        k = self.k if hasattr(self, "k") else 50.0  # steepness factor for entropy filtering

        with torch.no_grad():
            with open(file_path, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move tensors to device
                    output = output.to(self.device)
                    members = members.to(self.device)
                    targets = targets.to(self.device)

                    # If output is not already a probability distribution, you might do:
                    # output = F.softmax(output, dim=1)

                    # (A) Original entropies
                    orig_entropy = -torch.sum(output * torch.log(output + epsilon), dim=1)

                    # Separate members vs. non-members for original entropies
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    # Extend to CPU lists
                    members_orig_list.extend(orig_entropy[member_mask].cpu().numpy())
                    nonmembers_orig_list.extend(orig_entropy[non_member_mask].cpu().numpy())

                    # (B) Compute perturbed output using the same logic as in your test function
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]

                        # Overlap detection
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),
                            member_pvs.unsqueeze(0),
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)

                        temperature = 10.0
                        tau = 0.5
                        cos_thresh = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cos_thresh) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]

                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                        # Entropy filtering
                        entropy_vals = -torch.sum(tentative_perturbed * torch.log(tentative_perturbed + epsilon), dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy_vals, quantile_threshold)
                        entropy_mask = torch.sigmoid((entropy_vals - quantile_val) * k)

                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                        # Build the final perturbed output
                        perturbed_output = output.clone()
                        perturbed_output[non_member_indices] = perturbed_non_member_pvs
                    else:
                        # If no members or no non-members, just keep the output as-is
                        perturbed_output = output.clone()

                    # Normalize & clip
                    perturbed_output = torch.clamp(perturbed_output, min=1e-6, max=1)
                    perturbed_output = perturbed_output / perturbed_output.sum(dim=1, keepdim=True)

                    # (C) Perturbed entropies
                    pert_entropy = -torch.sum(perturbed_output * torch.log(perturbed_output + epsilon), dim=1)

                    # Separate members vs. non-members for perturbed entropies
                    members_pert_list.extend(pert_entropy[member_mask].cpu().numpy())
                    nonmembers_pert_list.extend(pert_entropy[non_member_mask].cpu().numpy())

        # If plot=True, we create two subplots: top for "before", bottom for "after"
        if plot:
            # Choose a style
            if "seaborn-darkgrid" in plt.style.available:
                plt.style.use("seaborn-darkgrid")
            elif "seaborn" in plt.style.available:
                plt.style.use("seaborn")
            else:
                plt.style.use("default")

            fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(8, 10), sharex=True)
            fig.suptitle("Entropy Distribution Before and After Perturbation", fontsize=16, fontweight="bold")

            # Colors
            color_members = "#E74C3C"     # Professional red
            color_nonmembers = "#2E86C1"  # Steel blue

            # Top subplot: original entropies
            axes[0].hist(members_orig_list, bins=50, alpha=0.5, label="Members (before)",
                        color=color_members, edgecolor="black")
            axes[0].hist(nonmembers_orig_list, bins=50, alpha=0.5, label="Non-members (before)",
                        color=color_nonmembers, edgecolor="black")
            axes[0].set_ylabel("Frequency", fontsize=13)
            axes[0].legend(fontsize=12)
            axes[0].grid(True, linestyle="--", alpha=0.5)
            axes[0].set_title("Before Perturbation", fontsize=14, fontweight="bold")

            # Bottom subplot: perturbed entropies
            axes[1].hist(members_pert_list, bins=50, alpha=0.7, label="Members (after)",
                        color=color_members, edgecolor="black")
            axes[1].hist(nonmembers_pert_list, bins=50, alpha=0.7, label="Non-members (after)",
                        color=color_nonmembers, edgecolor="black")
            axes[1].set_xlabel("Entropy", fontsize=13)
            axes[1].set_ylabel("Frequency", fontsize=13)
            axes[1].legend(fontsize=12)
            axes[1].grid(True, linestyle="--", alpha=0.5)
            axes[1].set_title("After Perturbation", fontsize=14, fontweight="bold")

            plt.tight_layout(rect=[0, 0, 1, 0.96])  # Leaves space for the suptitle
            if save_path is not None:
                plt.savefig(save_path, dpi=300)
            plt.show()

        # Return the arrays if you need them
        return (np.array(members_orig_list),
                np.array(nonmembers_orig_list),
                np.array(members_pert_list),
                np.array(nonmembers_pert_list))

    def approximate_perturbation_distribution(self):
        """
        Load all samples from self.ATTACK_SETS + "train.p" and separate them by membership.
        Then compute the per-group mean and standard deviation of the output vectors.
        Returns:
            member_mean, member_std, non_member_mean, non_member_std
        """
        member_samples = []
        non_member_samples = []
        
        file_path = self.ATTACK_SETS + "train.p"
        with open(file_path, "rb") as f:
            while True:
                try:
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break
                # Ensure output and members are on CPU.
                output = output.cpu()
                members = members.cpu()
                for i in range(output.size(0)):
                    if members[i].item() == 1:
                        member_samples.append(output[i])
                    else:
                        non_member_samples.append(output[i])
                        
        if member_samples:
            member_tensor = torch.stack(member_samples)
            member_mean = member_tensor.mean(dim=0)
            member_std = member_tensor.std(dim=0)
        else:
            member_mean, member_std = None, None

        if non_member_samples:
            non_member_tensor = torch.stack(non_member_samples)
            non_member_mean = non_member_tensor.mean(dim=0)
            non_member_std = non_member_tensor.std(dim=0)
        else:
            non_member_mean, non_member_std = None, None

        return member_mean, member_std, non_member_mean, non_member_std
    
    def compute_entropy_distribution(self, atk_model, prt_model, consin_thr, entrp_thr, entropy_dis_dr):
        """
        Computes and (optionally) plots the entropy distribution of the probability vectors (PVs)
        before and after perturbation. It uses the same perturbation procedure as in your test function.
        
        Args:
            dataset (str): Which dataset to use ("test" or "train"). Default is "test".
            plot (bool): Whether to plot the histogram of entropies.
            save_path (str): If provided, the histogram figure will be saved to this path.
        
        Returns:
            original_entropies (np.ndarray): Array of entropy values computed from original PVs.
            perturbed_entropies (np.ndarray): Array of entropy values computed from perturbed PVs.
        """
               
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)

        # Set models to evaluation mode.
        self.attack_model.eval()
        self.perturb_model.eval()

        epsilon = 1e-10
        original_entropy_list = []
        perturbed_entropy_list = []

        # Select the file based on dataset flag.
        # if dataset.lower() == "test":
        file_path = self.ATTACK_SETS + "test.p"
        # elif dataset.lower() == "train":
        #     file_path = self.ATTACK_SETS + "train.p"
        # else:
        #     raise ValueError("Dataset must be 'test' or 'train'.")

        with torch.no_grad():
            with open(file_path, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break

                    # Move data to device.
                    output = output.to(self.device)
                    # If output is not already probabilities, you might want to apply softmax:
                    # output = F.softmax(output, dim=1)
                    members = members.to(self.device)
                    targets = targets.to(self.device)

                    # Compute the original entropy for each sample.
                    # (Assumes output is a probability vector that sums to 1.)
                    orig_entropy = -torch.sum(output * torch.log(output + epsilon), dim=1)
                    original_entropy_list.append(orig_entropy.cpu())

                    # --- Compute the perturbed output using the same procedure as in test() ---
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)

                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]
                        
                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]
                        
                        # Overlap detection via cosine similarity.
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),
                            member_pvs.unsqueeze(0),
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)
                        
                        # Use Gumbel–Softmax to obtain binary selection.
                        temperature = 10.0
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]
                        
                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices].to(self.device))
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values
                        
                        # Entropy filtering:
                        entropy_vals = -torch.sum(tentative_perturbed * torch.log(tentative_perturbed + epsilon), dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy_vals, quantile_threshold)
                        # Use self.k (steepness factor) if defined; otherwise default to 50.
                        k = self.k
                        entropy_mask = torch.sigmoid((entropy_vals - quantile_val) * k)
                        
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values
                        
                        # Replace non-member outputs with perturbed ones.
                        perturbed_output = output.clone()
                        perturbed_output[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_output = output.clone()

                    # Normalize and clip (if needed).
                    perturbed_output = torch.clamp(perturbed_output, min=1e-6, max=1)
                    perturbed_output = perturbed_output / perturbed_output.sum(dim=1, keepdim=True)
                    # Compute perturbed entropy.
                    pert_entropy = -torch.sum(perturbed_output * torch.log(perturbed_output + epsilon), dim=1)
                    perturbed_entropy_list.append(pert_entropy.cpu())

            # Concatenate all batches.
            original_entropies = torch.cat(original_entropy_list, dim=0).numpy()
            perturbed_entropies = torch.cat(perturbed_entropy_list, dim=0).numpy()
            
        import numpy as np
        max_entropy = np.log2(self.num_classes)  # ≈ 3.3219
        original_entropies = original_entropies / max_entropy
        perturbed_entropies = perturbed_entropies / max_entropy

        # Plot settings as provided:
        size = 20
        params = {
            'axes.labelsize': size,
            'font.size': size,
            'legend.fontsize': size,
            'xtick.labelsize': size,
            'ytick.labelsize': size,
            'figure.figsize': [10, 8],
            "font.family": "arial",
        }
        plt.rcParams.update(params)

        # Create the figure and axis
        fig, ax = plt.subplots()

        # Define colors for the bars
        color_orig = "#2421f7"  # Blue for original entropies
        color_pert = "#f10219"  # Red for perturbed entropies

        # Compute histogram counts (not normalized to density)
        orig_counts, bin_edges = np.histogram(original_entropies, bins=20, density=False)
        pert_counts, _ = np.histogram(perturbed_entropies, bins=20, density=False)

        # Calculate bar width: split the bin width between the two sets of bars
        bin_width = bin_edges[1] - bin_edges[0]
        width_factor = 0.95  # Increase for thicker bars
        width = bin_width * width_factor / 2.0  # half width per bar

        # Enable grid lines and set grid behind the plot elements
        ax.grid(linestyle='dotted')
        ax.set_axisbelow(True)

        # Plot the histogram bars for original entropies
        ax.bar(
            bin_edges[:-1],
            orig_counts,
            width=width,
            color=color_orig,
            label="Before",
            align='edge'
        )

        # Plot the histogram bars for perturbed entropies, shifted to the right by 'width'
        ax.bar(
            bin_edges[:-1] + width,
            pert_counts,
            width=width,
            color=color_pert,
            label="After",
            align='edge'
        )

        # Set the x-axis label

        # Get handles and labels from the axis to create a legend
        handles, labels = ax.get_legend_handles_labels()
        legend = ax.legend(
            handles, 
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 1),  # Place the legend above the plot
            ncol=2,
            fontsize=size
        )
        # legend.get_frame().set_facecolor("0.95")
        legend.get_frame().set_edgecolor("0.91")

        # Adjust the layout to prevent clipping
        # plt.tight_layout()
        plt.tight_layout(rect=[0, 0, 1, 0.95])

        ax.set_xlabel("Prediction Uncertainty", fontsize=size)
        ax.set_ylabel("Frequency", fontsize=size)
        # plt.xlabel("False Positive Rate", )
        # plt.ylabel("True Positive Rate", fontsize=size)

        # Ensure the output directory exists
        os.makedirs(entropy_dis_dr, exist_ok=True)
        
        # Build the output path and save the figure
        output_path = os.path.join(entropy_dis_dr, self.dataset_name + "_entropy_dist.pdf")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Saved entropy distribution plot to {output_path}")
                
        return original_entropies, perturbed_entropies
    
    def compute_entropy_distribution_new(self, atk_model, prt_model, consin_thr, entrp_thr, entropy_dis_dr):
        """
        Computes and (optionally) plots the entropy distribution of the probability vectors (PVs)
        before and after perturbation, separately for members and non-members.
        
        The function:
        - Loads data from a file (assumed to be self.ATTACK_SETS + "test.p"),
        - Computes the original entropy for each sample,
        - Applies the perturbation procedure to non-member samples,
        - Computes the perturbed entropy,
        - Separates entropies by membership status,
        - Normalizes entropies by the maximum possible entropy (log2(num_classes)),
        - Plots subplots for "Before Perturbation" and "After Perturbation" showing histograms
            for members and non-members, and saves the figure.
        
        Returns:
            original_members, original_nonmembers, pert_members, pert_nonmembers : np.ndarray
        """
        # Set up the models and thresholds
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)
        self.attack_model.eval()
        self.perturb_model.eval()
        
        epsilon = 1e-10
        # Lists to store entropies for members and non-members (before and after perturbation)
        orig_members_list = []
        orig_nonmembers_list = []
        pert_members_list = []
        pert_nonmembers_list = []

        file_path = self.ATTACK_SETS + "test.p"
        
        with torch.no_grad():
            with open(file_path, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break
                    output = output.to(self.device)
                    members = members.to(self.device)
                    targets = targets.to(self.device)

                    # Compute original entropy: H = -sum(p * log(p))
                    orig_entropy = -torch.sum(output * torch.log(output + epsilon), dim=1)
                    # Separate based on membership flag (members==1)
                    orig_members = orig_entropy[members == 1]
                    orig_nonmembers = orig_entropy[members == 0]
                    orig_members_list.append(orig_members.cpu())
                    orig_nonmembers_list.append(orig_nonmembers.cpu())

                    # --- Perturbation procedure for non-members ---
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]
                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]
                        
                        # Overlap detection via cosine similarity.
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),
                            member_pvs.unsqueeze(0),
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)
                        
                        # Use Gumbel–Softmax for binary selection.
                        temperature = 10.0
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]
                        
                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices].to(self.device))
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values
                        
                        # Entropy filtering:
                        entropy_vals = -torch.sum(tentative_perturbed * torch.log(tentative_perturbed + epsilon), dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy_vals, quantile_threshold)
                        k = self.k  # steepness factor
                        entropy_mask = torch.sigmoid((entropy_vals - quantile_val) * k)
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values
                        
                        perturbed_output = output.clone()
                        perturbed_output[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_output = output.clone()
                    
                    perturbed_output = torch.clamp(perturbed_output, min=1e-6, max=1)
                    perturbed_output = perturbed_output / perturbed_output.sum(dim=1, keepdim=True)
                    pert_entropy = -torch.sum(perturbed_output * torch.log(perturbed_output + epsilon), dim=1)
                    # Separate perturbed entropies by membership.
                    pert_members = pert_entropy[members == 1]
                    pert_nonmembers = pert_entropy[members == 0]
                    pert_members_list.append(pert_members.cpu())
                    pert_nonmembers_list.append(pert_nonmembers.cpu())

        # Concatenate all batches.
        original_members = torch.cat(orig_members_list, dim=0).numpy()
        original_nonmembers = torch.cat(orig_nonmembers_list, dim=0).numpy()
        pert_members = torch.cat(pert_members_list, dim=0).numpy()
        pert_nonmembers = torch.cat(pert_nonmembers_list, dim=0).numpy()

        # Normalize entropies by the maximum possible entropy: log2(num_classes)
        max_entropy = np.log2(self.num_classes)
        original_members = original_members / max_entropy
        original_nonmembers = original_nonmembers / max_entropy
        pert_members = pert_members / max_entropy
        pert_nonmembers = pert_nonmembers / max_entropy

        # --- Plot settings ---
        size = 20
        params = {
            'axes.labelsize': size,
            'font.size': size,
            'legend.fontsize': size,
            'xtick.labelsize': size-5,
            'ytick.labelsize': size-5,
            'figure.figsize': [10, 8],
            "font.family": "arial",
        }
        plt.rcParams.update(params)

        # --- Create subplots: left for "Before", right for "After" ---
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        ax1.grid(linestyle='dotted')
        ax2.grid(linestyle='dotted')
        ax1.set_axisbelow(True)
        ax2.set_axisbelow(True)
        bins = 20

        # Left subplot: Original Entropies
        
        counts_orig_members, bin_edges = np.histogram(original_members, bins=bins, density=False)
        counts_orig_nonmembers, _ = np.histogram(original_nonmembers, bins=bins, density=False)
        bin_width = bin_edges[1] - bin_edges[0]
        width = bin_width * 0.95 / 2.0
        ax1.bar(bin_edges[:-1] - width/2, counts_orig_members, width=width,
                color="#2421f7", label="Members")
        ax1.bar(bin_edges[:-1] + width/2, counts_orig_nonmembers, width=width,
                color="#f10219", label="Non-Members")
        ax1.set_xlabel("Prediction Uncertainty", fontsize=size)
        ax1.set_ylabel("Frequency", fontsize=size)
        ax1.set_title("Before ", fontsize=size, fontweight="bold")
        ax1.legend(loc='upper center', ncol=2, bbox_to_anchor=(0.5, 1), fontsize=size)

        # Right subplot: Perturbed Entropies
        counts_pert_members, bin_edges = np.histogram(pert_members, bins=bins, density=False)
        counts_pert_nonmembers, _ = np.histogram(pert_nonmembers, bins=bins, density=False)
        ax2.bar(bin_edges[:-1] - width/2, counts_pert_members, width=width,
                color="#2421f7", label="Members")
        ax2.bar(bin_edges[:-1] + width/2, counts_pert_nonmembers, width=width,
                color="#f10219", label="Non-Members")
        ax2.set_xlabel("Prediction Uncertainty", fontsize=size)
        # ax2.set_ylabel("Frequency", fontsize=size)
        ax2.set_title("After", fontsize=size, fontweight="bold")
        # ax2.grid(linestyle='dotted')
        ax2.legend(loc='upper center', ncol=2, bbox_to_anchor=(0.5, 1), fontsize=size)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        os.makedirs(entropy_dis_dr, exist_ok=True)
        output_path = os.path.join(entropy_dis_dr, self.dataset_name + "_entropy_dist.pdf")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Saved entropy distribution plot to {output_path}")
        # return original_members, original_nonmembers, pert_members, pert_nonmembers

        # return original_entropies, perturbed_entropies
   
    def compute_entropy_distribution_new_norm(self, atk_model, prt_model, consin_thr, entrp_thr, entropy_dis_dr):
        """
        Computes and (optionally) plots the entropy distribution of the probability vectors (PVs)
        before and after perturbation, separately for members and non-members.
        
        The function:
        - Loads data from a file (assumed to be self.ATTACK_SETS + "test.p"),
        - Computes the original entropy for each sample,
        - Applies the perturbation procedure to non-member samples,
        - Computes the perturbed entropy,
        - Separates entropies by membership status,
        - Normalizes entropies by the maximum possible entropy (log2(num_classes)),
        - Plots subplots for "Before Perturbation" and "After Perturbation" showing normalized histograms
            for members and non-members, and saves the figure.
        
        Returns:
            original_members, original_nonmembers, pert_members, pert_nonmembers : np.ndarray
        """
        # Set up the models and thresholds
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)
        self.attack_model.eval()
        self.perturb_model.eval()
        
        epsilon = 1e-10
        # Lists to store entropies for members and non-members (before and after perturbation)
        orig_members_list = []
        orig_nonmembers_list = []
        pert_members_list = []
        pert_nonmembers_list = []

        file_path = self.ATTACK_SETS + "test.p"
        
        with torch.no_grad():
            with open(file_path, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break
                    output = output.to(self.device)
                    members = members.to(self.device)
                    targets = targets.to(self.device)

                    # Compute original entropy: H = -sum(p * log(p))
                    orig_entropy = -torch.sum(output * torch.log(output + epsilon), dim=1)
                    # Separate based on membership flag (members==1)
                    orig_members = orig_entropy[members == 1]
                    orig_nonmembers = orig_entropy[members == 0]
                    orig_members_list.append(orig_members.cpu())
                    orig_nonmembers_list.append(orig_nonmembers.cpu())

                    # --- Perturbation procedure for non-members ---
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]
                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]
                        
                        # Overlap detection via cosine similarity.
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),
                            member_pvs.unsqueeze(0),
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)
                        
                        # Use Gumbel–Softmax for binary selection.
                        temperature = 10.0
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]
                        
                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices].to(self.device))
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values
                        
                        # Entropy filtering:
                        entropy_vals = -torch.sum(tentative_perturbed * torch.log(tentative_perturbed + epsilon), dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy_vals, quantile_threshold)
                        k = self.k  # steepness factor
                        entropy_mask = torch.sigmoid((entropy_vals - quantile_val) * k)
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values
                        
                        perturbed_output = output.clone()
                        perturbed_output[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed_output = output.clone()
                    
                    perturbed_output = torch.clamp(perturbed_output, min=1e-6, max=1)
                    perturbed_output = perturbed_output / perturbed_output.sum(dim=1, keepdim=True)
                    pert_entropy = -torch.sum(perturbed_output * torch.log(perturbed_output + epsilon), dim=1)
                    # Separate perturbed entropies by membership.
                    pert_members = pert_entropy[members == 1]
                    pert_nonmembers = pert_entropy[members == 0]
                    pert_members_list.append(pert_members.cpu())
                    pert_nonmembers_list.append(pert_nonmembers.cpu())

        # Concatenate all batches.
        original_members = torch.cat(orig_members_list, dim=0).numpy()
        original_nonmembers = torch.cat(orig_nonmembers_list, dim=0).numpy()
        pert_members = torch.cat(pert_members_list, dim=0).numpy()
        pert_nonmembers = torch.cat(pert_nonmembers_list, dim=0).numpy()

        # Normalize entropies by the maximum possible entropy: log2(num_classes)
        max_entropy = np.log2(self.num_classes)
        original_members = original_members / max_entropy
        original_nonmembers = original_nonmembers / max_entropy
        pert_members = pert_members / max_entropy
        pert_nonmembers = pert_nonmembers / max_entropy



        size = 30
        params = {
            'axes.labelsize': size,
            'font.size': size,
            'legend.fontsize': size,
            'xtick.labelsize': size,
            'ytick.labelsize': size,
            'figure.figsize': [10, 8],
            "font.family": "arial",
        }
        plt.rcParams.update(params)

        # Create a single figure (no subplots)
        plt.figure()
        ax = plt.gca()

        # Enable grid and set it below plot elements.
        ax.grid(linestyle='dotted')
        ax.set_axisbelow(True)

        # Define histogram parameters.
        bins = 20
        # Compute normalized histograms for original_members and original_nonmembers.
        counts_orig_members, bin_edges = np.histogram(original_members, bins=bins, density=True)
        counts_orig_nonmembers, _ = np.histogram(original_nonmembers, bins=bins, density=True)
        bin_width = bin_edges[1] - bin_edges[0]
        width = bin_width * 0.95 / 2.0

        # Plot histogram bars.
        ax.bar(bin_edges[:-1] - width/2, counts_orig_members, width=width,
            color="#2421f7", label="Member")
        ax.bar(bin_edges[:-1] + width/2, counts_orig_nonmembers, width=width,
            color="#f10219", label="Non-Member")

        # Set labels and title.
        ax.set_xlabel("Prediction Uncertainty")
        ax.set_ylabel("Normalized Frequency")
        # ax.set_title("Before", fontweight="bold")

        # Set the legend in the lower right and customize its frame.
        legend = plt.legend(loc='upper center', ncol=2, bbox_to_anchor=(0.5, 1), fontsize=size-8)
        # ax1.legend(loc='upper center', ncol=2, bbox_to_anchor=(0.5, 1), fontsize=size)
        frame = legend.get_frame()
        frame.set_edgecolor("0.91")
        # Uncomment the next line if you wish to set a specific face color:
        # frame.set_facecolor('0.97')

        # Adjust subplot margin.
        plt.subplots_adjust(left=0.60)
        plt.tight_layout()

        # Define the output directory and file name.
        entropy_dis_dr = "./results"  # Update with your desired directory.
        os.makedirs(entropy_dis_dr, exist_ok=True)
        # Ensure that self.dataset_name exists; otherwise, replace it with a string.
        output_path = os.path.join(entropy_dis_dr, self.dataset_name + "_entropy_dist.pdf")

        # Save the figure as a PDF at 300 dpi.
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Saved entropy distribution plot to {output_path}")
       
    def compute_cosine_similarity_distribution(self, checkpoint_path, dataset="test", plot=True, save_path=None):
        """
        Loads the saved models and learned thresholds from checkpoint, then computes the cosine
        similarity between the original PVs and the perturbed PVs for each sample. It separates
        the similarity values for member and non-member samples.

        Args:
            checkpoint_path (str): Path to the checkpoint saved via save_att_per_thresholds_models.
            dataset (str): "test" or "train" to choose which dataset to use.
            plot (bool): Whether to plot the histogram of cosine similarities.
            save_path (str): If provided, the plot is saved to this file.

        Returns:
            member_similarities (np.ndarray): Cosine similarities for member samples.
            non_member_similarities (np.ndarray): Cosine similarities for non-member samples.
        """
        # Load checkpoint (using weights_only=True for security).
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        self.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
        self.cosine_threshold.data = checkpoint['cosine_threshold'].to(self.device)
        self.Entropy_quantile_threshold.data = checkpoint['Entropy_quantile_threshold'].to(self.device)
        
        self.attack_model.eval()
        self.perturb_model.eval()

        member_sim_list = []
        non_member_sim_list = []
        
        # Choose dataset file.
        if dataset.lower() == "test":
            file_path = self.ATTACK_SETS + "test.p"
        elif dataset.lower() == "train":
            file_path = self.ATTACK_SETS + "train.p"
        else:
            raise ValueError("Dataset must be 'test' or 'train'")
        
        with torch.no_grad():
            with open(file_path, "rb") as f:
                while True:
                    try:
                        output, prediction, members, targets = pickle.load(f)
                    except EOFError:
                        break
                    
                    output = output.to(self.device)
                    prediction = prediction.to(self.device)
                    members = members.to(self.device)
                    targets = targets.to(self.device)
                    
                    # Assume 'output' already represents a probability distribution.
                    original = output  # Original PVs

                    # Compute perturbed output using the same procedure as in test().
                    member_mask = (members == 1)
                    non_member_mask = (members == 0)
                    
                    if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                        member_indices = member_mask.nonzero(as_tuple=True)[0]
                        non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]
                        
                        member_pvs = output[member_indices]
                        non_member_pvs = output[non_member_indices]
                        
                        # Overlap detection via cosine similarity.
                        cos_sim = F.cosine_similarity(
                            non_member_pvs.unsqueeze(1),  # (n_non_members, 1, C)
                            member_pvs.unsqueeze(0),      # (1, n_members, C)
                            dim=2
                        )
                        max_cos_sim, _ = cos_sim.max(dim=1)  # (n_non_members,)
                        
                        # Gumbel–Softmax binary selection.
                        temperature = 10.0
                        tau = 0.5
                        cosine_threshold = torch.sigmoid(self.cosine_threshold)
                        logits = (max_cos_sim - cosine_threshold) * temperature
                        binary_logits = torch.stack([-logits, logits], dim=1)
                        gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                        binary_selection = gumbel_selection[:, 1]  # (n_non_members,)
                        
                        alpha = 1.0
                        learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                        tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values
                        
                        # Entropy filtering.
                        epsilon = 1e-10
                        entropy_vals = -torch.sum(tentative_perturbed * torch.log(tentative_perturbed + epsilon), dim=1)
                        quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                        quantile_val = torch.quantile(entropy_vals, quantile_threshold)
                        k = self.k if hasattr(self, "k") else 50.0
                        entropy_mask = torch.sigmoid((entropy_vals - quantile_val) * k)
                        
                        final_selection = binary_selection * entropy_mask
                        perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values
                        
                        # Construct perturbed output.
                        perturbed = output.clone()
                        perturbed[non_member_indices] = perturbed_non_member_pvs
                    else:
                        perturbed = output.clone()
                    
                    # Ensure perturbed output is normalized.
                    perturbed = torch.clamp(perturbed, min=1e-6, max=1)
                    perturbed = perturbed / perturbed.sum(dim=1, keepdim=True)
                    
                    # Now, compute cosine similarity for each sample between original and perturbed.
                    # This computes the cosine similarity for each row (sample).
                    sim = F.cosine_similarity(original, perturbed, dim=1)
                    
                    # Append the similarity values separately for members and non-members.
                    member_sim_list.append(sim[member_mask].cpu())
                    non_member_sim_list.append(sim[non_member_mask].cpu())
        

        
        if member_sim_list:
            member_similarities = torch.cat(member_sim_list, dim=0).numpy()
        else:
            member_similarities = np.array([])
        print(f"size: {member_similarities.size}")
        if non_member_sim_list:
            non_member_similarities = torch.cat(non_member_sim_list, dim=0).numpy()
        else:
            non_member_similarities = np.array([])

        print(f"First few member similarities: {member_similarities[:5]}")
        print(f"First few non-member similarities: {non_member_similarities[:5]}")
        exit()
        if plot:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(8,6))
            if member_similarities.size > 0:
                plt.hist(member_similarities, bins=50, alpha=0.5, label="Members (Unperturbed)", color="blue")
            if non_member_similarities.size > 0:
                plt.hist(non_member_similarities, bins=50, alpha=0.5, label="Non-Members (Perturbed)", color="orange")
            plt.xlabel("Cosine Similarity (Original vs. Perturbed)")
            plt.ylabel("Frequency")
            plt.title("Cosine Similarity Distribution Before and After Perturbation")
            plt.legend()
            if save_path is not None:
                plt.savefig(save_path)
            plt.show()

        return member_similarities, non_member_similarities
     
    def delete_pickle(self):
        train_file = glob.glob(self.ATTACK_SETS +"train.p")
        for trf in train_file:
            os.remove(trf)

        test_file = glob.glob(self.ATTACK_SETS +"test.p")
        for tef in test_file:
            os.remove(tef)

    def saveModel(self, path):
        torch.save(self.attack_model.state_dict(), path)
    
    def save_pertub_Model(self, path):
        torch.save(self.perturb_model.state_dict(), self.Perturb_MODELS_PATH)
    
    def save_att_per_thresholds_models(self, last_checkpoint, path):

        checkpoint = torch.load(last_checkpoint, weights_only=True)
        self.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
        self.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
        self.cosine_threshold = checkpoint['cosine_threshold']
        self.Entropy_quantile_threshold = checkpoint['entropy_threshold']
        
        models_threshold_params = {
            'attack_model_state_dict': self.attack_model.state_dict(),
            'perturb_model_state_dict': self.perturb_model.state_dict(),
            'cosine_threshold': self.cosine_threshold,
            'Entropy_quantile_threshold': self.Entropy_quantile_threshold
        }
        torch.save(models_threshold_params, path)
        
    def load_perturb_model(self):
        self.perturb_model.load_state_dict(torch.load(self.Perturb_MODELS_PATH, weights_only=True))
        self.perturb_model.eval()  # Set the generator to evaluation mode
        return self.perturb_model

    def visualize_transformed_pvs_classwise(self, target_class, atk_model, prt_model, consin_thr, entrp_thr, sub_folder):
       
        self.attack_model = atk_model
        self.perturb_model = prt_model
        self.cosine_threshold = torch.tensor(consin_thr, device=self.device)
        self.Entropy_quantile_threshold = torch.tensor(entrp_thr, device=self.device)

        self.perturb_model.eval()
        self.attack_model.eval()
        # Set professional style.
        sns.set_context("paper", font_scale=1.5)
        sns.set_style("whitegrid")

        # Storage for PVs, their target class labels, membership flags, and perturbation flags.
        original_pvs = []
        perturbed_pvs = []
        class_labels = []       # Target class for each sample.
        membership_flags = []   # 1 for member, 0 for non-member.
        perturb_flags = []      # For non-members: True if perturbed, False otherwise.

        with open(self.ATTACK_SETS + "test.p", "rb") as f:
            while True:
                try:
                    # Load batch data.
                    output, prediction, members, targets = pickle.load(f)
                except EOFError:
                    break  # End of file reached.

                # Move tensors to device.
                output = output.to(self.device)
                prediction = prediction.to(self.device)
                members = members.to(self.device)
                targets = targets.to(self.device)

                # Initialize a per-batch perturbation flag (False by default).
                batch_perturb_flags = torch.zeros_like(members, dtype=torch.bool)
                # Make a copy for the perturbed output.
                perturbed_output = output.clone()

                # Create masks for members and non-members.
                member_mask = (members == 1)
                non_member_mask = (members == 0)

                if member_mask.sum() > 0 and non_member_mask.sum() > 0:
                    # Get indices for members and non-members.
                    member_indices = member_mask.nonzero(as_tuple=True)[0]
                    non_member_indices = non_member_mask.nonzero(as_tuple=True)[0]

                    # Extract corresponding probability vectors (PVs).
                    member_pvs = output[member_indices]       # (n_members, C)
                    non_member_pvs = output[non_member_indices] # (n_non_members, C)

                    # ----- Step 2: Overlap Detection via Cosine Similarity -----
                    # Compute cosine similarity between each non-member and each member.
                    cos_sim = F.cosine_similarity(
                        non_member_pvs.unsqueeze(1),  # (n_non_members, 1, C)
                        member_pvs.unsqueeze(0),      # (1, n_members, C)
                        dim=2
                    )
                    # For each non-member, take the maximum cosine similarity with any member.
                    max_cos_sim, _ = cos_sim.max(dim=1)  # (n_non_members,)

                    # ----- Step 3: Differentiable Binary Selection using Gumbel–Softmax -----
                    temperature = 10.0  # scaling factor for logits
                    tau = 0.5           # Gumbel–Softmax temperature (lower -> sharper)
                    # Reparameterize the cosine threshold so it lies in (0,1).
                    

                    cosine_threshold = torch.sigmoid(self.cosine_threshold)
                    logits = (max_cos_sim - cosine_threshold) * temperature  # (n_non_members,)
                    binary_logits = torch.stack([-logits, logits], dim=1)      # (n_non_members, 2)
                    gumbel_selection = F.gumbel_softmax(binary_logits, tau=tau, hard=True)
                    binary_selection = gumbel_selection[:, 1]  # (n_non_members,)

                    alpha = 1.0

                    # ----- Step 4: Perturbation with Entropy Filtering -----
                    # Compute the learned perturbations for all non-member PVs.
                    # (For visualization we use no_grad(), so gradients are not tracked.)
                    learned_values = self.perturb_model(non_member_pvs, targets[non_member_indices])
                    # Compute a tentative perturbed output.
                    tentative_perturbed = non_member_pvs + alpha * binary_selection.unsqueeze(1) * learned_values

                    # Compute the entropy of each tentative perturbed non-member PV.
                    epsilon = 1e-10
                    entropy = - (tentative_perturbed * torch.log(tentative_perturbed + epsilon)).sum(dim=1).to(self.device)  # (n_non_members,)

                    # Select top samples based on entropy.
                    # For example, use a quantile threshold (self.Entropy_quantile_threshold should be a float in (0,1)).
                    # quantile_val = torch.quantile(entropy, 0.25)
                    quantile_threshold = torch.sigmoid(self.Entropy_quantile_threshold)
                    quantile_val = torch.quantile(entropy, quantile_threshold)

                    # Use a sigmoid to generate a soft entropy mask.
                    # self.k controls the steepness; if not defined, default to 50.0.
                    # k = self.k if hasattr(self, "k") else 50.0
                    entropy_mask = torch.sigmoid((entropy - quantile_val) * self.k)
                    # Combine the binary selection with the entropy mask.
                    final_selection = binary_selection * entropy_mask
                    # Compute final perturbed non-member PVs.
                    perturbed_non_member_pvs = non_member_pvs + alpha * final_selection.unsqueeze(1) * learned_values

                    # Replace the non-member PVs in the overall output with the final perturbed versions.
                    perturbed_output[non_member_indices] = perturbed_non_member_pvs
                    # Mark these non-members as perturbed if final_selection > 0.5.
                    batch_perturb_flags[non_member_indices] = (final_selection > 0.5)
                else:
                    perturbed_output = output.clone()

                # Append data from this batch.
                original_pvs.append(output.detach().cpu().numpy())
                perturbed_pvs.append(perturbed_output.detach().cpu().numpy())
                class_labels.append(targets.detach().cpu().numpy())
                membership_flags.append(members.detach().cpu().numpy())
                perturb_flags.append(batch_perturb_flags.detach().cpu().numpy())

        # Convert lists to arrays.
        if not (original_pvs and perturbed_pvs and class_labels and membership_flags and perturb_flags):
            print("No PVs selected for visualization.")
            return

        original_pvs = np.vstack(original_pvs)        # (total_samples, C)
        perturbed_pvs = np.vstack(perturbed_pvs)        # (total_samples, C)
        class_labels = np.hstack(class_labels)          # (total_samples,)
        membership_flags = np.hstack(membership_flags)  # (total_samples,)
        perturb_flags = np.hstack(perturb_flags)        # (total_samples,)

        # ----- Filter to Only Include the Target Class -----
        target_mask = (class_labels == target_class)
        if np.sum(target_mask) == 0:
            print(f"No samples found for target class {target_class}.")
            return
        original_pvs = original_pvs[target_mask]
        perturbed_pvs = perturbed_pvs[target_mask]
        class_labels = class_labels[target_mask]
        membership_flags = membership_flags[target_mask]
        perturb_flags = perturb_flags[target_mask]

        # ----- t-SNE Dimensionality Reduction -----
        reducer = TSNE(n_components=2, perplexity=30, learning_rate=200, random_state=42)
        # Stack original and perturbed PVs.
        all_pvs = np.vstack([original_pvs, perturbed_pvs])
        reduced_pvs = reducer.fit_transform(all_pvs)

        num_samples = original_pvs.shape[0]
        original_pvs_2d = reduced_pvs[:num_samples]
        perturbed_pvs_2d = reduced_pvs[num_samples:]

        # Define colors and markers.
        palette = {
            "Members": "#1f77b4",      # Blue
            "Non-Members": "#ff7f0e",  # Orange
        }

        # ----- Plotting with Seaborn -----
       # --- Create subplots ---
       # --- Global Plot Settings with Arial Font ---
        size = 20
        params = {
            'axes.labelsize': size,
            'font.size': size,
            'legend.fontsize': size,
            'xtick.labelsize': size,
            'ytick.labelsize': size,
            'figure.figsize': [16, 8],
            "font.family": "arial",
        }
        plt.rcParams.update(params)

        # --- Create Two Subplots ---
        fig, ax = plt.subplots(1, 2, figsize=(16, 8))

        # Left subplot: Before Perturbation
        sns.scatterplot(
            x=original_pvs_2d[:, 0], y=original_pvs_2d[:, 1],
            hue=np.where(membership_flags == 1, "Members", "Non-Members"),
            palette=palette, alpha=0.7, s=100, edgecolor='black',
            ax=ax[0]
        )
        ax[0].set_title("Before", fontsize=20, fontweight='bold')
        ax[0].set_xlabel("t-SNE Component 1", fontsize=20)
        ax[0].set_ylabel("t-SNE Component 2", fontsize=20)
        ax[0].grid(True, linestyle="--", alpha=0.5)
        # Remove local legend
        if ax[0].get_legend():
            ax[0].get_legend().remove()

        # Right subplot: After Perturbation
        sns.scatterplot(
            x=perturbed_pvs_2d[:, 0], y=perturbed_pvs_2d[:, 1],
            hue=np.where(membership_flags == 1, "Members", "Non-Members"),
            palette=palette, alpha=0.7, s=100, edgecolor='black',
            ax=ax[1]
        )
        ax[1].set_title("After", fontsize=20, fontweight='bold')
        ax[1].set_xlabel("t-SNE Component 1", fontsize=20)
        # ax[1].set_ylabel("t-SNE Component 2", fontsize=20)
        ax[1].grid(True, linestyle="--", alpha=0.5)

        # Overlay a highlight for perturbed non-members on the "After" subplot.
        non_member_mask = (membership_flags != 1) & (perturb_flags == 1)
        ax[1].scatter(
            perturbed_pvs_2d[non_member_mask, 0],
            perturbed_pvs_2d[non_member_mask, 1],
            facecolors='#ff7f0e',    # no fill
            edgecolors='red',     # red outline
            s=100,                # larger markers
            marker='o',
            label='Perturbed Non-Members'
        )
        # Remove local legend if exists
        if ax[1].get_legend():
            ax[1].get_legend().remove()

        # --- Combine Legend Entries from Both Subplots ---
        handles_left, labels_left = ax[0].get_legend_handles_labels()
        handles_right, labels_right = ax[1].get_legend_handles_labels()
        combined_handles = []
        combined_labels = []
        for h, l in zip(handles_left + handles_right, labels_left + labels_right):
            if l not in combined_labels:
                combined_handles.append(h)
                combined_labels.append(l)

        # --- Create a Global Legend Below the X-Axis ---
        fig.legend(
            combined_handles, combined_labels,
            loc='lower center',
            ncol=len(combined_labels),
            fontsize=20,
            bbox_to_anchor=(0.5, 0.02)  # adjust the y-value as needed
        )

        # Adjust layout to make room for the legend
        # plt.tight_layout(rect=[0, 0.1, 1, 1])

        # Adjust layout to make room for the global legend.
        plt.tight_layout(rect=[0, 0.08, 1, 1])

        # plt.tight_layout()

        # plt.suptitle(f"t-SNE Visualization of PVs for Target Class {target_class}\nMembers and Non-Members", 
                    # fontsize=16, fontweight='bold')
        # plt.show()

        # 9. Save the plot in sub_folder with a name referencing the class label.
        plot_filename = f"class_{target_class}.pdf"
        save_path_full = os.path.join(sub_folder, plot_filename)
        # plt.savefig(save_path_full)
        plt.savefig(save_path_full, dpi=300, format='pdf')
        plt.close()
        # plt.show()
    
    def metric_results(fpr_list, tpr_list, thresholds):
        fprs = [0.01,0.001,0.0001,0.00001,0.0] # 1%, 0.1%, 0.01%, 0.001%, 0%
        tpr_dict = {}
        thresholds_dict = {}
        acc = np.max(1 - (fpr_list + (1 - tpr_list)) / 2)
        roc_auc = auc(fpr_list, tpr_list)

        for fpr in fprs:
            tpr_dict[fpr] = tpr_list[np.where(fpr_list <= fpr)[0][-1]] # tpr at fpr
            thresholds_dict[fpr] = thresholds[np.where(fpr_list <= fpr)[0][-1]] # corresponding threshold

        return roc_auc, acc, tpr_dict, thresholds_dict

    def get_attack_dataset_without_shadow(train_set, test_set, batch_size):
        mem_length = int(len(train_set)*0.45)
        nonmem_length = int(len(test_set)*0.45)
        mem_train, mem_test, _ = torch.utils.data.random_split(train_set, [mem_length, mem_length, len(train_set)-(mem_length*2)])
        nonmem_train, nonmem_test, _ = torch.utils.data.random_split(test_set, [nonmem_length, nonmem_length, len(test_set)-(nonmem_length*2)])
        mem_train, mem_test, nonmem_train, nonmem_test = list(mem_train), list(mem_test), list(nonmem_train), list(nonmem_test)

        for i in range(len(mem_train)):
            mem_train[i] = mem_train[i] + (1,)
        for i in range(len(nonmem_train)):
            nonmem_train[i] = nonmem_train[i] + (0,)
        for i in range(len(nonmem_test)):
            nonmem_test[i] = nonmem_test[i] + (0,)
        for i in range(len(mem_test)):
            mem_test[i] = mem_test[i] + (1,)
            
        attack_train = mem_train + nonmem_train
        attack_test = mem_test + nonmem_test

        attack_trainloader = torch.utils.data.DataLoader(
            attack_train, batch_size=batch_size, shuffle=True, num_workers=1, persistent_workers=True)
        attack_testloader = torch.utils.data.DataLoader(
            attack_test, batch_size=batch_size, shuffle=True, num_workers=1, persistent_workers=True)

        return attack_trainloader, attack_testloader


def get_attack_dataset_with_shadow(target_train, target_test, shadow_train, shadow_test, batch_size):
    mem_train, nonmem_train, mem_test, nonmem_test = list(shadow_train), list(shadow_test), list(target_train), list(target_test)

    for i in range(len(mem_train)):
        mem_train[i] = mem_train[i] + (1,)
    for i in range(len(nonmem_train)):
        nonmem_train[i] = nonmem_train[i] + (0,)
    for i in range(len(nonmem_test)):
        nonmem_test[i] = nonmem_test[i] + (0,)
    for i in range(len(mem_test)):
        mem_test[i] = mem_test[i] + (1,)


    train_length = min(len(mem_train), len(nonmem_train))
    test_length = min(len(mem_test), len(nonmem_test))

    mem_train, _ = torch.utils.data.random_split(mem_train, [train_length, len(mem_train) - train_length])
    non_mem_train, _ = torch.utils.data.random_split(nonmem_train, [train_length, len(nonmem_train) - train_length])
    mem_test, _ = torch.utils.data.random_split(mem_test, [test_length, len(mem_test) - test_length])
    non_mem_test, _ = torch.utils.data.random_split(nonmem_test, [test_length, len(nonmem_test) - test_length])
    
    attack_train = mem_train + non_mem_train
    attack_test = mem_test + non_mem_test

    attack_trainloader = torch.utils.data.DataLoader(
        attack_train, batch_size=batch_size, shuffle=True, num_workers=1, persistent_workers=True)
    attack_testloader = torch.utils.data.DataLoader(
        attack_test, batch_size=batch_size, shuffle=True, num_workers=1, persistent_workers=True)

    return attack_trainloader, attack_testloader

def dataloader_to_dataset(dataloader):
    data_list = []
    
    for batch in dataloader:
        data, labels = batch  # assuming the data is returned as (data, labels)
        data_list.append(data)
    
    # Concatenate all the batches into one dataset
    full_data = torch.cat(data_list, dim=0)
    
    return full_data

def save_best_checkpoint(val_loss, attack_model, perturb_model, cosine_threshold, entropy_threshold, checkpoint_path):
    checkpoint = {
        'val_loss': val_loss,
        'attack_model_state_dict': attack_model.state_dict(),
        'perturb_model_state_dict': perturb_model.state_dict(),
        'cosine_threshold': cosine_threshold,
        'entropy_threshold': entropy_threshold
    }
    torch.save(checkpoint, checkpoint_path)
    print(f"Checkpoint saved to {checkpoint_path}")

# attack_mode0_com(PATH + "_target.pth", PATH + "_shadow.pth",  PATH, device, attack_trainloader, attack_testloader, target_model, shadow_model, attack_model, perturb_model, num_classes, mode, dataset_name, attack_name, entropy_dis_dr, apcmia_cluster, arch, acc_gap)
def attack_mode0_com(TARGET_PATH, SHADOW_PATH, ATTACK_PATH, device, attack_trainloader, attack_testloader, target_model, shadow_model, attack_model, perturb_model, num_classes, mode, dataset_name, attack_name, entropy_dis_dr, apcmia_cluster, arch, acc_gap):
    MODELS_PATH = ATTACK_PATH + "_meminf_"+attack_name+"_.pth"
    Perturb_MODELS_PATH = ATTACK_PATH + "_perturb_model.pth"

    RESULT_PATH = ATTACK_PATH + "_meminf_attack0_com.p"
    RESULT_PATH_csv = ATTACK_PATH + "_meminf_attack0_com.csv"
    
    ATTACK_SETS = ATTACK_PATH + "_meminf_attack_mode0__com"
    ATTACK_SETS_PV_CSV = ATTACK_PATH + "_meminf_attack_pvs.csv"

    fpr_tpr_file_path = ATTACK_PATH + "_FPR_TPR_" + attack_name + "_.csv"


    
    MODELS_PATH_att_per_thr = ATTACK_PATH + "_attack_pertubr_thresholds_"+attack_name+".pth" # will store all 


    print(f"MODELS_PATH: {MODELS_PATH}, \nRESULT_PATH: {RESULT_PATH}, \nATTACK_PATH: {ATTACK_SETS}")
    
    epoch_data = []
    train_accuracy_list = []
    test_accuracy_list = []
    res_list = []
    cosine_entropy_threshold_list = []
    
    
        
    attack = attack_for_blackbox_com_NEW(TARGET_PATH,SHADOW_PATH, Perturb_MODELS_PATH,  ATTACK_SETS,ATTACK_SETS_PV_CSV, attack_trainloader, attack_testloader, target_model, shadow_model, attack_model,perturb_model, device, dataset_name, attack_name, num_classes, acc_gap)
           
    if 1:
        
        get_attack_set = 1;
        if get_attack_set:
            attack.delete_pickle()
            
            dataset = attack.prepare_dataset() # uses shahow model to first obtain PVs and and the, combines it into [Pv, prediction, members, targets]
           
   
        
        epochs = 100
       
        checkpoint_files = []  # List to store unique checkpoint filenames
        res_list = []  # store final test metrics per epoch

       
            
        threshold_progress = []  # list of tuples (cosine_threshold, entropy_threshold)
        test_loss_progress = []  # list of average test losses
        
        # initialize the early_stopping object
        if dataset_name == "purchase":
            patience = 7
        else:
            patience = 15

        early_stopping = EarlyStopping(patience=patience, verbose=True)

        for ep in range(epochs):
            flag = 1 if ep == (epochs - 1) else 0
            print("Epoch %d:" % (ep + 1))
            # Train for one epoch
            res_train = attack.train(flag, RESULT_PATH, RESULT_PATH_csv, mode)
            # Test for one epoch and get metrics (the last element is avg test loss)
            res_test, fpr, tpr = attack.test(flag, RESULT_PATH, mode)
            # Extract current threshold values (after sigmoid)
            current_cosine_threshold = torch.sigmoid(attack.cosine_threshold).item()
            current_entropy_threshold = torch.sigmoid(attack.Entropy_quantile_threshold).item()
                                    
            res_list.append({'epoch': ep + 1,                                
                            'test_acc': res_test[0]*100,
                            'test_prec': res_test[1]*100,
                            'test_recall': res_test[2]*100,
                            'test_f1': res_test[3]*100,
                            'test_auc': res_test[4]*100,
                            'test_loss': res_test[-1],
                            'cosine_threshold': current_cosine_threshold,
                            'entropy_threshold': current_entropy_threshold})

            
            early_stopping(res_test[-1], attack.attack_model)

            # Suppose early_stopping has an attribute best_loss that is updated when improvement occurs:
            if res_test[-1] == early_stopping.best_val_loss:
              
                checkpoint_path = f'checkpoint_epoch_{ep+1}.pt'
                
                save_best_checkpoint(
                    res_test[-1],
                    attack.attack_model,
                    attack.perturb_model,
                    current_cosine_threshold,
                    current_entropy_threshold,
                    checkpoint_path=checkpoint_path
                )
                checkpoint_files.append(checkpoint_path)
            
            if early_stopping.early_stop:
                print("Early stopping")
                break
        
        if checkpoint_files:
            last_checkpoint = checkpoint_files[-1]
            checkpoint = torch.load(last_checkpoint, map_location=device, weights_only=True)
            attack.attack_model.load_state_dict(checkpoint['attack_model_state_dict'])
            attack.perturb_model.load_state_dict(checkpoint['perturb_model_state_dict'])
            best_cosine_threshold = checkpoint['cosine_threshold']
            best_entropy_threshold = checkpoint['entropy_threshold']
            print(f"Loaded last checkpoint: {last_checkpoint}")
           

        print(f"Best Cosine Threshold: {best_cosine_threshold:.4f}, Best Entropy Threshold: {best_entropy_threshold:.4f}")
       
        # Optionally, save the threshold and loss progress to a CSV.
        df = pd.DataFrame(res_list)
        file_path = ATTACK_SETS + f"_Results-Mean_mode-{attack_name}_.csv" 
        df.to_csv(file_path, index=False)
       
        attack.save_att_per_thresholds_models(last_checkpoint, MODELS_PATH_att_per_thr)
        print(f'models and thresholds are savedQ')
        
        # the following function will load the thresholds from MODELS_PATH_att_per_thr
        
        if attack_name == "apcmia":
            print(f'computing ROC for apcmia')
            attack.test_saved_model_apcmia(attack.attack_model, attack.perturb_model,best_cosine_threshold,best_entropy_threshold)
            # and dataset_name != "adult"
            if(dataset_name != "cifar10" and dataset_name != "cifar100" and dataset_name != "stl10" and dataset_name != "purchase" and dataset_name != "texas" and dataset_name != "adult" and dataset_name != "location"):
                fpr, tpr, thresholds, roc_auc = attack.compute_roc_curve_apcmia(attack.attack_model, attack.perturb_model,best_cosine_threshold,best_entropy_threshold)
           
            attack.compute_entropy_distribution_new_norm(attack.attack_model, attack.perturb_model,best_cosine_threshold,best_entropy_threshold, entropy_dis_dr)


        else:
            # attack.test_saved_model_rest(MODELS_PATH_att_per_thr, plot=True, save_path=None)
            attack.test_saved_model_rest(attack.attack_model)
            # exit()
            fpr, tpr, thresholds, roc_auc = attack.compute_roc_curve_rest(attack.attack_model)

        # Save fpr and tpr to a CSV file
        df_fpr_tpr = pd.DataFrame({'FPR': fpr, 'TPR': tpr})
        df_fpr_tpr.to_csv(fpr_tpr_file_path, index=False) # roc call won't work now cuz name has added timestamp
        print(f"saved ROC curve info")

        
  
    
    if attack_name == "apcmia" and apcmia_cluster:

          # 1. Create the root directory "cluster_results" if it doesn't exist.
        cluster_root = f"cluster_results/{arch}/"
        if not os.path.exists(cluster_root):
            os.makedirs(cluster_root)

        # 2. Create a subdirectory for this dataset (e.g., "test") inside "cluster_results".
        sub_folder = os.path.join(cluster_root, dataset_name)
        if not os.path.exists(sub_folder):
            os.makedirs(sub_folder)

        for target_class in range(num_classes):
            attack.visualize_transformed_pvs_classwise(target_class, attack.attack_model, attack.perturb_model, best_cosine_threshold, best_entropy_threshold, sub_folder)
       