const { expect } = require("chai");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");
const { ethers } = require("hardhat");

describe("PaymentExecutor item-level idempotency", function () {
  it("rejects duplicate execution for the same executionItemId", async function () {
    const [operator, beneficiary] = await ethers.getSigners();

    const DemoToken = await ethers.getContractFactory("DemoToken");
    const initialSupply = ethers.parseUnits("1000000", 18);
    const token = await DemoToken.deploy("Demo USDT", "dUSDT", 18, initialSupply);
    await token.waitForDeployment();

    const PaymentExecutor = await ethers.getContractFactory("PaymentExecutor");
    const executor = await PaymentExecutor.deploy();
    await executor.waitForDeployment();

    const tokenAddress = await token.getAddress();
    const executorAddress = await executor.getAddress();
    const executeWithItem = executor.getFunction(
      "executePayment(bytes32,bytes32,address,address,uint256,string,uint256,uint256)"
    );
    const amount = ethers.parseUnits("100", 18);
    const executionItemId = ethers.keccak256(ethers.toUtf8Bytes("execution-item-1"));
    const orderId = ethers.keccak256(ethers.toUtf8Bytes("order-1"));

    await (await token.approve(executorAddress, amount * 2n)).wait();

    await expect(
      executeWithItem(
        executionItemId,
        orderId,
        tokenAddress,
        beneficiary.address,
        amount,
        "INV-001",
        1,
        1
      )
    )
      .to.emit(executor, "PaymentExecuted")
      .withArgs(
        orderId,
        executionItemId,
        tokenAddress,
        beneficiary.address,
        amount,
        "INV-001",
        1,
        1,
        operator.address,
        anyValue,
        anyValue
      );

    expect(await executor.executedItems(executionItemId)).to.equal(true);
    expect(await token.balanceOf(beneficiary.address)).to.equal(amount);

    await expect(
      executeWithItem(
        executionItemId,
        orderId,
        tokenAddress,
        beneficiary.address,
        amount,
        "INV-001",
        1,
        1
      )
    ).to.be.revertedWith("execution item already executed");
  });

  it("allows multiple splits for the same order with different executionItemIds", async function () {
    const [, beneficiary] = await ethers.getSigners();

    const DemoToken = await ethers.getContractFactory("DemoToken");
    const initialSupply = ethers.parseUnits("1000000", 18);
    const token = await DemoToken.deploy("Demo USDT", "dUSDT", 18, initialSupply);
    await token.waitForDeployment();

    const PaymentExecutor = await ethers.getContractFactory("PaymentExecutor");
    const executor = await PaymentExecutor.deploy();
    await executor.waitForDeployment();

    const tokenAddress = await token.getAddress();
    const executorAddress = await executor.getAddress();
    const executeWithItem = executor.getFunction(
      "executePayment(bytes32,bytes32,address,address,uint256,string,uint256,uint256)"
    );
    const orderId = ethers.keccak256(ethers.toUtf8Bytes("order-split"));
    const item1 = ethers.keccak256(ethers.toUtf8Bytes("order-split-item-1"));
    const item2 = ethers.keccak256(ethers.toUtf8Bytes("order-split-item-2"));
    const amount = ethers.parseUnits("50", 18);

    await (await token.approve(executorAddress, amount * 2n)).wait();

    await expect(
      executeWithItem(item1, orderId, tokenAddress, beneficiary.address, amount, "INV-SPLIT", 1, 2)
    ).to.not.be.reverted;
    await expect(
      executeWithItem(item2, orderId, tokenAddress, beneficiary.address, amount, "INV-SPLIT", 2, 2)
    ).to.not.be.reverted;

    expect(await executor.executedItems(item1)).to.equal(true);
    expect(await executor.executedItems(item2)).to.equal(true);
    expect(await token.balanceOf(beneficiary.address)).to.equal(amount * 2n);
  });
});
