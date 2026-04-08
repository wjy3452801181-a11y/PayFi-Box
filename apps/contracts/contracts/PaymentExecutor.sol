// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

contract PaymentExecutor {
    address public immutable operator;
    mapping(bytes32 => bool) public executedItems;

    event PaymentExecuted(
        bytes32 indexed orderId,
        bytes32 indexed executionItemId,
        address token,
        address indexed beneficiary,
        uint256 amount,
        string referenceText,
        uint256 splitIndex,
        uint256 splitCount,
        address operator,
        uint256 timestamp,
        bytes32 paymentRef
    );

    constructor() {
        operator = msg.sender;
    }

    function executePayment(
        bytes32 executionItemId,
        bytes32 orderId,
        address token,
        address beneficiary,
        uint256 amount,
        string calldata referenceText,
        uint256 splitIndex,
        uint256 splitCount
    ) external returns (bytes32 paymentRef) {
        paymentRef = _executePayment(
            executionItemId,
            orderId,
            token,
            beneficiary,
            amount,
            referenceText,
            splitIndex,
            splitCount
        );
    }

    function executePayment(
        bytes32 orderId,
        address token,
        address beneficiary,
        uint256 amount,
        string calldata referenceText,
        uint256 splitIndex,
        uint256 splitCount
    ) external returns (bytes32 paymentRef) {
        bytes32 derivedExecutionItemId = keccak256(
            abi.encodePacked(orderId, token, beneficiary, amount, referenceText, splitIndex, splitCount)
        );
        paymentRef = _executePayment(
            derivedExecutionItemId,
            orderId,
            token,
            beneficiary,
            amount,
            referenceText,
            splitIndex,
            splitCount
        );
    }

    function _executePayment(
        bytes32 executionItemId,
        bytes32 orderId,
        address token,
        address beneficiary,
        uint256 amount,
        string calldata referenceText,
        uint256 splitIndex,
        uint256 splitCount
    ) internal returns (bytes32 paymentRef) {
        require(msg.sender == operator, "only operator");
        require(!executedItems[executionItemId], "execution item already executed");
        require(token != address(0), "token is zero");
        require(beneficiary != address(0), "beneficiary is zero");
        require(amount > 0, "amount is zero");
        require(splitIndex > 0, "splitIndex invalid");
        require(splitCount >= splitIndex, "splitCount invalid");

        executedItems[executionItemId] = true;

        bool ok = IERC20(token).transferFrom(msg.sender, beneficiary, amount);
        require(ok, "transferFrom failed");

        paymentRef = keccak256(
            abi.encodePacked(
                orderId,
                token,
                beneficiary,
                amount,
                referenceText,
                splitIndex,
                splitCount,
                msg.sender,
                block.timestamp
            )
        );

        emit PaymentExecuted(
            orderId,
            executionItemId,
            token,
            beneficiary,
            amount,
            referenceText,
            splitIndex,
            splitCount,
            msg.sender,
            block.timestamp,
            paymentRef
        );
    }
}
